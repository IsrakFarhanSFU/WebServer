# Name: <Israk Farhan>   Student number: <301412948>
"""CMPT 371 Project 1 - HTTP/1.1 client on a raw TCP socket.

Usage: python3 client.py --host H --port P --path /a [--path /b] [--out FILE ...]
"""

import argparse
import socket
import sys


def parse_args(argv):
    """TASK 4. Parse --host (default 127.0.0.1), --port (int), --path
    (repeatable), --out (repeatable, paired with --path in order)."""

    parser = argparse.ArgumentParser()

    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--path", action="append", required=True)
    parser.add_argument("--out", action="append", default=[])

    args = parser.parse_args(argv)

    if len(args.out) > len(args.path):
        parser.error("More output files than paths")

    return args


def send_request(sock, host, path):
    """TASK 4. Send one GET request line, a Host header, and the blank line
    that ends it."""

    request = ("GET %s HTTP/1.1\r\nHost: %s\r\n\r\n") % (path, host)

    sock.sendall(request.encode("ascii"))


def read_head(sock, pending):
    """TASK 4. Read until the blank line ending the response head.
    Return (head_bytes, leftover) where leftover is body already received. The
    leftover is the start of the body and cannot be read again, so it must be
    counted toward Content-Length rather than discarded."""

    data = pending

    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)

        if not chunk:
            raise ConnectionError(
                "Connection closed before header response complete")

        data += chunk

    head, _, leftover = data.partition(b"\r\n\r\n")

    return head, leftover


def parse_head(head):
    """TASK 4. Split a response head into (status_code, reason, headers).
    headers is a dict with lower-cased names."""

    lines = head.decode("iso-8859-1").split("\r\n")

    parts = lines[0].split(" ", 2)

    if len(parts) != 3 or not parts[0].startswith("HTTP/"):
        raise ValueError("Malformed status line")

    version, code, reason = parts
    status_code = int(code)

    headers = {}

    for line in lines[1:]:
        if ":" not in line:
            raise ValueError("Malformed response header")

        name, value = line.split(":", 1)

        headers[name.strip().lower()] = value.strip()

    return status_code, reason, headers


def read_body(sock, length, pending):
    """TASK 4. Return exactly length body bytes, counting what is already in
    pending, plus any bytes left over past them. Do not read until the connection
    closes: the server keeps it open, so a read-to-EOF client never returns.
    Every check in task 4 runs against a server that holds the connection open
    for a full minute, so reading to EOF fails all four, not just the timing
    one."""

    body = bytearray(pending[:length])
    leftover = pending[length:]

    while len(body) < length:
        chunk = sock.recv(4096)

        if not chunk:
            raise ConnectionError(
                "Connection closed before body response complete")

        remaining = length - len(body)

        body.extend(chunk[:remaining])
        leftover += chunk[remaining:]

    return bytes(body), leftover


def main(argv=None):
    """TASK 4. Connect once, then for each --path in turn: send the request,
    read the head, read exactly Content-Length bytes, print
    '<status> <reason> <n> bytes', and write the body to the matching --out file.
    Return 0 on success. All the paths travel over the one connection, so
    whatever is left in the buffer past one body is the start of the next
    response."""

    args = parse_args(argv)

    try:
        with socket.create_connection(
            (args.host, args.port), timeout=5) as sock:
            
            pending = b""

            for i, path in enumerate(args.path):
                send_request(sock, args.host, path)

                head, pending = read_head(sock, pending)
                status, reason, headers = parse_head(head)

                if "content-length" not in headers:
                    raise ValueError("Missing Content-Length")

                length = int(headers["content-length"])

                if length < 0:
                    raise ValueError("Invalid Content-Length")

                body, pending = read_body(sock, length, pending)

                print("%d %s %d bytes" % (status, reason, len(body)))

                if i < len(args.out):
                    with open(args.out[i], "wb") as f:
                        f.write(body)

        return 0

    except (OSError, ValueError) as error:
        print("Client error: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
