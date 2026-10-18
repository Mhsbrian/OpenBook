#!/usr/bin/env python3
"""Serve doc-fonts-test.html on 127.0.0.1:PORT and save the JSON it POSTs to /report as OUT, then exit
(ANAL-208; scripts/ui/doc-fonts-check.sh runs it behind `adb reverse`).

usage: doc-fonts-serve.py PORT OUT [TIMEOUT_S]
"""
import http.server
import os
import sys
import threading

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doc-fonts-test.html")


def main(argv):
    port, out = int(argv[1]), argv[2]
    timeout = float(argv[3]) if len(argv) > 3 else 180
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] != "/doc-fonts-test.html":
                self.send_error(404)
                return
            with open(PAGE, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/report":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            with open(out, "wb") as f:
                f.write(body)
            self.send_response(204)
            self.end_headers()
            done.set()

        def log_message(self, fmt, *args):
            sys.stderr.write("doc-fonts-serve: " + fmt % args + "\n")

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ok = done.wait(timeout)
    srv.shutdown()
    if not ok:
        sys.stderr.write("doc-fonts-serve: no report after %g s\n" % timeout)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
