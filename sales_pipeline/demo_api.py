"""Loopback-only HTTP API serving explicitly synthetic sales fixtures."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

FIXTURE = Path(__file__).resolve().parent.parent / 'data' / 'synthetic_orders.json'


def make_server(port=0, fixture=FIXTURE):
    records = json.loads(Path(fixture).read_text())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != '/orders':
                self.send_error(404)
                return
            try:
                page = int(parse_qs(parsed.query).get('page', ['1'])[0])
                if page < 1:
                    raise ValueError()
            except ValueError:
                self.send_error(400, 'page must be a positive integer')
                return
            start = (page - 1) * 4
            body = json.dumps({'items': records[start:start + 4],
                               'next_page': page + 1 if start + 4 < len(records) else None}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)
