#!/usr/bin/env python3
"""Serve docs/ locally with Cache-Control: no-cache.

The plain ``python3 -m http.server`` sends no caching header, so browsers cache
each ES module heuristically from its Last-Modified age. After an edit, a long
unchanged module can then be reused stale beside a freshly loaded one, which
breaks imports of newly added exports. ``no-cache`` makes every load revalidate
(unchanged files still return 304). Standard library only::

    python3 tools/serve.py            # http://127.0.0.1:8770/
    python3 tools/serve.py --port 9000
"""
import argparse
import functools
import http.server
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"


class Server(http.server.ThreadingHTTPServer):
    # The default listen backlog of 5 resets connections when Chrome loads modules and tiles in a burst.
    request_queue_size = 128


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    handler = functools.partial(NoCacheHandler, directory=str(DOCS))
    with Server((args.bind, args.port), handler) as server:
        print(f"Serving {DOCS} at http://{args.bind}:{args.port}/ (no-cache)", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
