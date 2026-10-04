"""Render static reports or serve one page on loopback; no execution endpoints."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from quant_research.__main__ import publish_report
from quant_research.serde import InputError
from .render import render_page, read_report

MAX_PAGE = 32 * 1024 * 1024


def read_page(path):
    if not Path(path).is_file():
        raise InputError('page must be a regular local file')
    with Path(path).open('rb') as handle:
        page = handle.read(MAX_PAGE + 1)
    if len(page) > MAX_PAGE:
        raise InputError('page exceeds size limit')
    return page


def make_server(page, *, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlsplit(self.path).path not in ('/', '/index.html'):
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(page)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format, *args):
            pass

    return HTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only completed offline report viewer.')
    commands = parser.add_subparsers(dest='command', required=True)
    render = commands.add_parser('render')
    render.add_argument('--research', type=Path, required=True)
    render.add_argument('--control', type=Path, action='append', default=[])
    render.add_argument('--output', type=Path, required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--page', type=Path, required=True)
    serve.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == 'render':
            if os.path.lexists(args.output) or not args.output.parent.is_dir():
                raise InputError('output exists or parent missing')
            report, digest = read_report(args.research)
            controls = [read_report(path)[0] for path in args.control]
            publish_report(args.output, render_page(report, controls, report_sha256=digest))
            print(f'Wrote read-only offline view: {args.output}')
            return 0
        if not 0 <= args.port <= 65535:
            raise InputError('invalid port')
        page = read_page(args.page)
        with make_server(page, port=args.port) as server:
            print(f'Offline view: http://127.0.0.1:{server.server_address[1]}', flush=True)
            server.serve_forever()
    except (InputError, OSError) as error:
        print(f'view error: {error}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    sys.exit(main())
