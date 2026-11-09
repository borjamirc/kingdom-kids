#!/usr/bin/env python3
"""
Static dev server for the game.

Same as `python -m http.server`, but it prints the LAN URL for testing on a
phone and sends no-store so the phone cannot serve a stale sheet or script.

Usage:
    python tools/serve.py [--port 8000] [--host 0.0.0.0]
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # The phone should never serve a stale sheet or script from cache.
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        super().end_headers()

    def log_message(self, fmt, *args):
        # Quiet by default: a single page load is ~30 asset requests. Errors
        # still surface through log_error, which does not route through here.
        pass


def lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return ips


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--host', default='0.0.0.0')
    args = ap.parse_args()

    if not os.path.isfile('index.html'):
        print('error: run this from the repo root', file=sys.stderr)
        return 1

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print('serving %s on port %d' % (os.getcwd(), args.port))
    for ip in lan_ips():
        print('  phone:  http://%s:%d' % (ip, args.port))
    print('  local:  http://localhost:%d' % args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
