#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Serve one signed OTA payload to the laptop's update_engine over HTTP, for the duration of one update.

update_engine streams A/B payloads over HTTP and asks for byte ranges, so this
answers Range requests (206 with Content-Range) as well as whole-file GETs and
HEAD. It serves exactly payload.bin and payload_properties.txt from one
directory and nothing else, binds to one address, logs every request, and stops
after --idle-seconds without a request or on SIGINT/SIGTERM.

The payload's integrity does not depend on this transport: update_engine checks
its signature against the installed OpenBook certificate and the FILE_HASH /
METADATA_HASH headers before it switches slots.

usage: serve-payload.py --dir SIGNED_DIR --bind 192.168.50.10 --port 8090 [--idle-seconds 900]
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import signal
import sys
import threading
import time

SERVED = ("payload.bin", "payload_properties.txt")


def parse_range(header, size):
    """'bytes=a-b' / 'bytes=a-' / 'bytes=-n' -> (start, end) inclusive, or None if unsatisfiable."""
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    if m.group(1) == "":
        n = int(m.group(2))
        if n == 0:
            return None
        return max(0, size - n), size - 1
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else size - 1
    if start >= size or end < start:
        return None
    return start, min(end, size - 1)


def handler_for(root, state):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            state["last"] = time.monotonic()
            print(json.dumps(dict(t=time.strftime("%H:%M:%S"), client=self.client_address[0],
                                  request=self.requestline, msg=fmt % args)), flush=True)

        def _file(self):
            name = self.path.split("?", 1)[0].lstrip("/")
            if name not in SERVED:
                self.send_error(404)
                return None
            return root / name

        def _serve(self, body):
            path = self._file()
            if path is None:
                return
            size = path.stat().st_size
            rng = self.headers.get("Range")
            start, end, code = 0, size - 1, 200
            if rng:
                r = parse_range(rng, size)
                if r is None:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start, end, code = r[0], r[1], 206
            self.send_response(code)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if not body:
                return
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left:
                    chunk = f.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
                    state["bytes"] += len(chunk)
                    state["last"] = time.monotonic()

        def do_GET(self):
            self._serve(True)

        def do_HEAD(self):
            self._serve(False)

    return Handler


def serve(root, bind, port, idle_seconds, ready=None):
    for name in SERVED:
        if not (root / name).is_file():
            raise SystemExit(f"missing {root / name}")
    state = dict(last=time.monotonic(), bytes=0)
    httpd = ThreadingHTTPServer((bind, port), handler_for(root, state))
    httpd.daemon_threads = True
    stop = threading.Event()

    def watchdog():
        while not stop.wait(1):
            if time.monotonic() - state["last"] > idle_seconds:
                httpd.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    if ready:
        ready(httpd.server_address)
    print(json.dumps(dict(serving=[str(root / n) for n in SERVED], bind=bind, port=httpd.server_address[1],
                          idle_seconds=idle_seconds)), flush=True)
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        stop.set()
        httpd.server_close()
    print(json.dumps(dict(stopped=True, bytes_sent=state["bytes"])), flush=True)
    return state["bytes"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", type=Path, required=True, help="build-ruby-ab-ota.py OUT/signed")
    p.add_argument("--bind", required=True, help="host address on the laptop's network (not 0.0.0.0)")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--idle-seconds", type=int, default=900)
    a = p.parse_args()
    if a.bind in ("0.0.0.0", "::"):
        p.error("bind to the one address the laptop reaches, not every interface")
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    try:
        serve(a.dir, a.bind, a.port, a.idle_seconds)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
