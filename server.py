# Name: <Israk Farhan>   Student number: <301412948>
"""CMPT 371 Project 1 - static HTTP/1.1 server on raw TCP sockets.

Usage: python3 server.py --port PORT --root DIR [--workers N]
"""

import argparse
import mimetypes
import os
import queue
import socket
import sys
import threading
import time
from email.utils import formatdate

KNOWN_METHODS = {"GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "TRACE", "CONNECT"}

requests_served = 0
counter_lock = threading.Lock()


def parse_args(argv):
    """TASK 1. Parse --port (int, 0 means pick any free port), --root
    (directory), --workers (int, how many threads the pool starts with,
    default 8). Accept --workers from task 1 even though nothing uses it until
    task 5: every command in the handout passes it."""

    parser = argparse.ArgumentParser()

    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--workers", type=int, default=8)

    return parser.parse_args(argv)


def recv_request_head(conn):
    """TASK 3. Call recv() repeatedly until the blank line that ends the header
    block has arrived. Return the head bytes including that blank line, or None
    if the client closed the connection first.
    In task 1 handle_connection may read the head with a single recv(); this is
    what replaces that call, and is where reading becomes correct."""

    head = bytearray()

    while not head.endswith(b"\r\n\r\n"):
        chunk = conn.recv(1)

        if not chunk:
            return None

        head.extend(chunk)

    return bytes(head)


def parse_request(head):
    """TASK 3. Split a header block into (method, target, version, headers).
    headers is a dict with lower-cased names. Raise ValueError if the request
    line is not three fields or a header line has no colon; handle_request turns
    that into a 400."""

    lines = head.split(b"\r\n\r\n", 1)[0].split(b"\r\n")

    parts = lines[0].decode("ascii").split(" ")

    if len(parts) != 3 or not all(parts):
        raise ValueError("Malformed request line")

    method, target, version = parts

    headers = {}

    for line in lines[1:]:
        if b":" not in line:
            raise ValueError("Malformed header line")

        name, value = line.split(b":", 1)

        name = name.decode("ascii").strip().lower()
        value = value.decode("iso-8859-1").strip()

        if not name:
            raise ValueError("Empty header name")

        headers[name] = value

    return method, target, version, headers
    


def resolve_path(root, target):
    """TASK 1. Turn a request target into an absolute path inside root: drop any
    query string, percent-decode, append index.html for a target ending in '/'.
    Return None if the target is malformed.
    All three rules are graded: /index.html?x=1 and /index.html are the same
    file, / is that directory's index.html, and /page/sub.html works."""

    if not target.startswith("/"):
            return None
    
    target = target.split("?", 1)[0]  # drop query string
    
    decoded = bytearray()
    i = 0
    
    while i < len(target):
        if target[i] == "%":
            if i + 2 >= len(target):
                return None
            try:
                decoded.append(int(target[i + 1:i + 3], 16))
            except ValueError:
                return None
            i += 3
        else:
            decoded.extend(target[i].encode("utf-8"))
            i += 1
    
    try:
        target = decoded.decode("utf-8")
    except UnicodeDecodeError:
        return None
    
    if "\x00" in target:
        return None
    
    if target.endswith("/"):
        target += "index.html"
    
    root = os.path.abspath(root)
    path = os.path.realpath(os.path.join(root, target.lstrip("/")))
    
    if os.path.commonpath([root, path]) != root:
        return None
    
    return path


def build_response(status, reason, body, content_type, extra=None):
    """TASK 1. Return the full response as bytes: status line, the Date, Server,
    Content-Type, Content-Length and Connection headers, any extra headers,
    a blank line, then body.
    Every response goes through here, including 404, 400, 405 and 501, so every
    response carries all five headers. Content-Length is the number of body
    bytes that follow, and nothing else."""

    lines = [
        "HTTP/1.1 %d %s" % (status, reason),
        "Date: %s" % formatdate(usegmt=True),
        "Server: CMPT 371 Project 1",
        "Content-Type: %s" % content_type,
        "Content-Length: %d" % len(body),
        "Connection: keep-alive",
    ]
    if extra is not None:
        for name, value in extra.items():
            lines.append("%s: %s" % (name, value))

    head = "\r\n".join(lines) + "\r\n\r\n"

    return head.encode("ascii") + body


def handle_request(head, root):
    """TASK 1, extended in tasks 2 and 3. Turn one header block into a complete
    response.
    Task 1: 200 and 404. Task 2: HEAD, which carries no body, and Content-Type
    from the file extension. Task 3: 400 (malformed request line or header line,
    no Host), 405 (POST and the other known methods, with Allow: GET, HEAD) and
    501 (a token that is not an HTTP method)."""

    try:
        method, target, version, headers = parse_request(head)
    except ValueError:
        return build_response(400, "Bad Request", 
                              b"400 Bad Request\n", "text/plain")

    if not headers.get("host"):
        return build_response(400, "Bad Request", 
                              b"400 Bad Request\n", "text/plain")

    unsupported = ("POST", "PUT", "DELETE",
                    "OPTIONS", "PATCH", "TRACE", "CONNECT")

    if method in unsupported:
        return build_response(405, "Method Not Allowed", 
                              b"405 Method Not Allowed\n", "text/plain",
                              {"Allow": "GET, HEAD"})

    if method not in ("GET", "HEAD"):
        return build_response(501, "Not Implemented", 
                              b"501 Not Implemented\n", "text/plain")

    path = resolve_path(root, target)

    if path is None or not os.path.isfile(path):
        body = b"404 Not Found\n"
        response = build_response(404, "Not Found", body, "text/plain")
    else:
        with open(path, "rb") as f:
            body = f.read()

        content_type, encoding = mimetypes.guess_type(path)

        if content_type is None:
            content_type = "application/octet-stream"

        response = build_response(200, "OK", body, content_type)

    if method == "HEAD":
        response_head = response.split(b"\r\n\r\n", 1)[0]
        return response_head + b"\r\n\r\n"

    return response

def handle_connection(conn, root):
    """TASK 1, extended in tasks 3 and 5. Serve requests on one connection until
    the client closes it or it goes idle -- a few seconds; five is reasonable.
    Task 1: read the head (one recv() is enough for now), call handle_request,
    sendall() the response, and loop. Task 3: replace that read with
    recv_request_head. Task 5: after each response, increment requests_served
    under counter_lock and print 'served <n>' to stderr, where n is the value
    this request produced, read inside the same lock that incremented it."""

    global requests_served
    
    conn.settimeout(5)

    try:
        while True:
            try:
                head = recv_request_head(conn)
            except socket.timeout:
                break

            if head is None:
                break

            response = handle_request(head, root)
            conn.sendall(response)

            with counter_lock:
                requests_served += 1
                mine = requests_served
            
            print("served %d" % mine, file=sys.stderr, flush=True)

    finally:
        conn.close()


def worker(work_queue, root):
    """TASK 5. Take accepted connections off work_queue and serve them, forever.
    Every worker thread runs this; none of them is created per connection.
    Nothing before task 5 calls this, and main must not start any worker threads
    until you write it."""

    while True:
        conn = work_queue.get()
        
        try:
            handle_connection(conn, root)
        finally:
            work_queue.task_done()


def main(argv=None):
    """TASK 1, replaced in task 5. Bind 127.0.0.1 on the requested port, listen,
    print the port line below, then serve connections.
    Task 1: accept one connection at a time and pass each to handle_connection.
    Task 5: replace that loop -- create --workers threads running worker() and a
    queue.Queue, and let main do nothing but accept and enqueue."""
    # Given. The grading script reads this line to find your server, so print it
    # exactly as written, immediately after listen(), and keep flush=True.
    #     print("Listening on port %d" % listener.getsockname()[1], flush=True)
    
    args = parse_args(argv)

    work_queue = queue.Queue()

    for _ in range(args.workers):
        thread = threading.Thread(
            target=worker, args=(work_queue, args.root))
        thread.daemon = True
        thread.start()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", args.port))
    listener.listen()

    print("Listening on port %d" % listener.getsockname()[1], flush=True)

    try:
        while True:
            conn, addr = listener.accept()
            work_queue.put(conn)

    finally:
        listener.close()

if __name__ == "__main__":
    main()
