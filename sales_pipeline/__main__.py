"""Run with python3 -m sales_pipeline; no package installation needed."""
import argparse
import json
import logging
from threading import Thread
from .demo_api import make_server
from .pipeline import run_pipeline, reports


def main():
    parser = argparse.ArgumentParser(description='Synthetic sales ETL learning project')
    parser.add_argument('--verbose', action='store_true')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('demo', 'run', 'report'):
        command = sub.add_parser(name)
        command.add_argument('--db', default='var/sales.db')
        if name == 'run':
            command.add_argument('--base-url', required=True)
            command.add_argument('--timeout', type=float, default=3)
            command.add_argument('--attempts', type=int, default=3)
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        if args.command == 'serve':
            with make_server(args.port) as server:
                print('SYNTHETIC API: http://127.0.0.1:%s/orders?page=1' % server.server_port, flush=True)
                server.serve_forever()
        elif args.command == 'demo':
            with make_server() as server:
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    summary = run_pipeline('http://127.0.0.1:%s' % server.server_port, args.db)
                finally:
                    server.shutdown()
                    worker.join()
            print(json.dumps({'summary': summary, 'reports': reports(args.db)}, indent=2))
        elif args.command == 'run':
            print(json.dumps(run_pipeline(args.base_url, args.db, timeout=args.timeout, attempts=args.attempts), indent=2))
        else:
            print(json.dumps(reports(args.db), indent=2))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logging.error('%s', exc)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
