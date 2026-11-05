import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from sales_pipeline.demo_api import make_server
from sales_pipeline.extract import fetch_orders
from sales_pipeline.pipeline import run_pipeline, reports
from sales_pipeline.transform import clean_record

BASE = dict(line_id='L1', order_id='O1', sold_on='2026-01-01', product=' Pen ', quantity=2, unit_price='1.20', currency=' usd ')
def response(payload):
    return io.BytesIO(json.dumps(payload).encode())

class CleaningTests(unittest.TestCase):
    def test_clean_money_and_text(self):
        row = clean_record(BASE)
        self.assertEqual((row['product'], row['currency'], row['unit_price_cents']), ('Pen', 'USD', 120))

    def test_invalid_records(self):
        for change in [dict(quantity=True), dict(quantity=0), dict(quantity='2'), dict(unit_price='NaN'), dict(unit_price='Infinity'), dict(unit_price='-1'), dict(unit_price='1.234'), dict(unit_price=1.2), dict(sold_on='2026-02-30'), dict(product=' '), dict(currency='EUR')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                clean_record(dict(BASE, **change))
        with self.assertRaises(ValueError):
            clean_record(None)

class ExtractionTests(unittest.TestCase):
    @patch('sales_pipeline.extract.time.sleep')
    @patch('sales_pipeline.extract.urlopen')
    def test_retry_then_paginate(self, request, sleep):
        request.side_effect = [HTTPError('url', 503, 'unavailable', {}, None), response({'items': [BASE], 'next_page': 2}), response({'items': [], 'next_page': None})]
        self.assertEqual(fetch_orders('http://example.invalid'), [BASE])
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_count, 1)

    @patch('sales_pipeline.extract.time.sleep')
    @patch('sales_pipeline.extract.urlopen')
    def test_timeout_exhaustion(self, request, sleep):
        request.side_effect = TimeoutError('slow API')
        with self.assertRaises(TimeoutError):
            fetch_orders('http://example.invalid', attempts=3, timeout=0.1)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args.kwargs['timeout'], 0.1)
        self.assertEqual(sleep.call_count, 2)

    @patch('sales_pipeline.extract.time.sleep')
    @patch('sales_pipeline.extract.urlopen')
    def test_rate_limit_and_connection_retry(self, request, sleep):
        request.side_effect = [HTTPError('url', 429, 'rate limit', {}, None), URLError('offline'), response({'items': [], 'next_page': None})]
        self.assertEqual(fetch_orders('http://example.invalid'), [])
        self.assertEqual(request.call_count, 3)

    @patch('sales_pipeline.extract.urlopen')
    def test_client_error_not_retried(self, request):
        request.side_effect = HTTPError('url', 404, 'missing', {}, None)
        with self.assertRaises(HTTPError):
            fetch_orders('http://example.invalid')
        self.assertEqual(request.call_count, 1)

    @patch('sales_pipeline.extract.urlopen')
    def test_bad_contract_and_page_limit(self, request):
        for payload in [{'items': []}, {'items': {}, 'next_page': None}, {'items': [], 'next_page': 1}]:
            request.return_value = response(payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                fetch_orders('http://example.invalid')
        request.return_value = response({'items': [], 'next_page': 2})
        with self.assertRaisesRegex(ValueError, 'max_pages'):
            fetch_orders('http://example.invalid', max_pages=1)
        request.return_value = io.BytesIO(b'not JSON')
        with self.assertRaises(ValueError):
            fetch_orders('http://example.invalid')

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'sales.db'
    def tearDown(self):
        self.temp.cleanup()

    def test_real_http_end_to_end_and_rerun(self):
        with make_server() as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = 'http://127.0.0.1:%s' % server.server_port
                first = run_pipeline(url, self.db)
                second = run_pipeline(url, self.db)
            finally:
                server.shutdown()
                worker.join()
        self.assertEqual((first['fetched'], first['inserted'], first['duplicates'], first['rejected']), (11, 4, 1, 6))
        self.assertEqual((second['inserted'], second['duplicates'], second['rejected']), (0, 5, 6))
        self.assertEqual([r['revenue_cents'] for r in reports(self.db)['daily_sales']], [1260, 1650])
        self.assertEqual(reports(self.db)['top_products'][0]['product'], 'Notebook')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sales').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM rejections').fetchone()[0], 12)

    @patch('sales_pipeline.pipeline.fetch_orders')
    def test_failed_extraction_keeps_existing_sales(self, fetch):
        fetch.return_value = [BASE]
        run_pipeline('unused', self.db)
        fetch.side_effect = TimeoutError('API timed out')
        with self.assertRaises(TimeoutError):
            run_pipeline('unused', self.db)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sales').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT status FROM runs ORDER BY run_id DESC LIMIT 1').fetchone()[0], 'failed')

    @patch('sales_pipeline.pipeline.fetch_orders')
    def test_unexpected_load_failure_rolls_back(self, fetch):
        fetch.return_value = [BASE, dict(BASE, line_id='L2')]
        with patch('sales_pipeline.pipeline.clean_record', side_effect=[clean_record(BASE), RuntimeError('simulated bug')]):
            with self.assertRaises(RuntimeError):
                run_pipeline('unused', self.db)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sales').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT status, inserted FROM runs').fetchone(), ('failed', 0))

    @patch('sales_pipeline.pipeline.fetch_orders', return_value=[])
    def test_empty_source(self, fetch):
        self.assertEqual(run_pipeline('unused', self.db)['fetched'], 0)
        self.assertEqual(reports(self.db)['daily_sales'], [])

if __name__ == '__main__':
    unittest.main()
