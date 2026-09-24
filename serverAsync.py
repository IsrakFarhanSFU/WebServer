# Name: <Israk Farhan>   Student number: <301412948>

"""CMPT 371 Project 1 - Bonus 2: Asynchronous Web Server."""

import argparse
import socket
import selectors
import server


def parse_args(argv=None):
    """Parse the server port and document root."""

    parser = argparse.ArgumentParser()

    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--root", required=True)

    return parser.parse_args(argv)


def receive_request(conn, state):
    """Read available bytes and extract complete HTTP requests."""

    try:
        chunk = conn.recv(4096)
    except BlockingIOError:
        return True

    if not chunk:
        return False

    state["incoming"].extend(chunk)

    while b"\r\n\r\n" in state["incoming"]:
        end = state["incoming"].index(b"\r\n\r\n") + 4

        head = bytes(state["incoming"][:end])

        # Preserve bytes beyond this request.
        del state["incoming"][:end]

        state["requests"].append(head)

    return True


def prepare_responses(state, root):
    """Generate responses for all complete requests."""

    while state["requests"]:
        head = state["requests"].pop(0)

        response = server.handle_request(head, root)

        state["outgoing"].extend(response)


def send_pending(conn, state):
    """Send available response bytes without blocking."""

    if not state["outgoing"]:
        return

    try:
        sent = conn.send(state["outgoing"])

    except BlockingIOError:
        return

    if sent == 0:
        raise ConnectionError("Connection closed during send")

    del state["outgoing"][:sent]

def main(argv=None):
    """Start a single-threaded, non-blocking TCP listener."""

    args = parse_args(argv)

    selector = selectors.DefaultSelector()

    listener = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        listener.bind(("127.0.0.1", args.port))
        listener.listen()
        listener.setblocking(False)

        selector.register(
            listener,
            selectors.EVENT_READ
        )

        print(
            "Listening on port %d" %
            listener.getsockname()[1],
            flush=True
        )

        while True:
            events = selector.select()

            for key, mask in events:
                if key.fileobj is listener:
                    try:
                        conn, addr = listener.accept()
                    except BlockingIOError:
                        continue

                    conn.setblocking(False)

                    state = {
                        "incoming": bytearray(),
                        "requests": [],
                        "outgoing": bytearray(),
                        "read_closed": False
                    }

                    selector.register(
                        conn,
                        selectors.EVENT_READ,
                        data=state
                    )

                else:
                    conn = key.fileobj
                    state = key.data

                    try:
                        if mask & selectors.EVENT_READ:
                            alive = receive_request(conn, state)

                            prepare_responses(state, args.root)

                            if not alive:
                                state["read_closed"] = True

                        if mask & selectors.EVENT_WRITE:
                            send_pending(conn, state)

                        if state["read_closed"] and not state["outgoing"]:
                            selector.unregister(conn)
                            conn.close()
                            continue

                        events = 0

                        if not state["read_closed"]:
                            events |= selectors.EVENT_READ

                        if state["outgoing"]:
                            events |= selectors.EVENT_WRITE

                        selector.modify(conn, events, data=state)

                    except (OSError, ValueError, UnicodeError):
                        selector.unregister(conn)
                        conn.close()

    finally:
        selector.close()
        listener.close()


if __name__ == "__main__":
    main()