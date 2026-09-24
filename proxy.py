# Name: <Israk Farhan>   Student number: <301412948>

"""CMPT 371 Project 1 - Bonus 1: Caching Web Proxy."""

import argparse
import socket
import sys
from time import time
import client
import server
import os
import hashlib


def parse_args(argv=None):
    """Parse the proxy port and origin server address."""

    parser = argparse.ArgumentParser()

    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--origin-host", required=True)
    parser.add_argument("--origin-port", type=int, required=True)

    return parser.parse_args(argv)

def fetch_from_origin(host, port, path):
    """Fetch the resource from the origin server and return the response bytes."""

    with socket.create_connection((host, port), timeout=5) as origin:
        
        client.send_request(origin, host, path)
        head, pending = client.read_head(origin, b"")
        status, reason, headers = client.parse_head(head)

        if "content-length" not in headers:
            raise ValueError("Origin response missing Content-Length")

        length = int(headers["content-length"])

        if length < 0:
            raise ValueError("Invalid Content-Length")

        body, leftover = client.read_body(origin, length, pending)

        return head + b"\r\n\r\n" + body

CACHE_DIR = "proxy-cache"

def cache_paths(target):
    """Create safe filenames for a cached HTTP response."""

    key = hashlib.sha256(target.encode("utf-8")).hexdigest()

    head_file = os.path.join(CACHE_DIR, key + ".head")
    body_file = os.path.join(CACHE_DIR, key + ".body")

    return head_file, body_file

def get_response(origin_host, origin_port, target):
    """Return a cached response or fetch and cache a new one."""

    head_file, body_file = cache_paths(target)

    if os.path.isfile(head_file) and os.path.isfile(body_file):
        with open(head_file, "rb") as f:
            head = f.read()

        with open(body_file, "rb") as f:
            body = f.read()
            
        return head + b"\r\n\r\n" + body

    response = fetch_from_origin(origin_host, origin_port, target)

    head, _, body = response.partition(b"\r\n\r\n")

    if head.startswith(b"HTTP/1.1 200"):
        os.makedirs(CACHE_DIR, exist_ok=True)

        with open(head_file, "wb") as f:
            f.write(head)

        with open(body_file, "wb") as f:
            f.write(body)
    
    return response

def handle_client(conn, origin_host, origin_port):
    """Handle a single client connection: read the request, fetch from origin, and send back the response."""

    conn.settimeout(5)

    with conn:
        while True:
            try:
                head = server.recv_request_head(conn)
                
                if head is None:
                    break  

                try:
                    method, target, version, headers = server.parse_request(head)
                except ValueError:
                    response = server.make_response(400, "Bad Request",
                                                     b"400 Bad Request\n", "text/plain")
                    conn.sendall(response)
                    continue

                if not headers.get("host"):
                    response = server.make_response(
                        400, "Bad Request", 
                        b"400 Bad Request\n", "text/plain")
                    conn.sendall(response)
                    continue

                if method != "GET":
                    response = server.build_response(
                        405, "Method Not Allowed", 
                        b"405 Method Not Allowed\n", "text/plain",
                        {"Allow": "GET"})
                    conn.sendall(response)
                    continue

                response = get_response(
                    origin_host, origin_port, target)

                conn.sendall(response)

            except (OSError, ConnectionError):
                break

def main(argv=None):
    """Run the caching proxy server."""

    args = parse_args(argv)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        listener.bind(("127.0.0.1", args.port))
        listener.listen()

        print("Listening on port %d" %
            listener.getsockname()[1],
            flush=True)

        while True:
            conn, addr = listener.accept()
            
            handle_client(conn, args.origin_host, args.origin_port)
    finally:
        listener.close()

if __name__ == "__main__":
    main()