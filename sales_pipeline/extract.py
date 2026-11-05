"""Read a paginated JSON API, retrying only transient failures."""
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

LOG = logging.getLogger(__name__)


def fetch_orders(base_url, timeout=3.0, attempts=3, backoff=0.2, max_pages=100):
    """Contract: GET /orders?page=N -> {"items": [...], "next_page": N+1 or null}.

    Extract everything before loading; an incomplete API response never loads sales.
    Memory use grows with input size. This intentional limit suits a learning project.
    """
    if timeout <= 0 or attempts < 1 or backoff < 0 or max_pages < 1:
        raise ValueError("timeout/attempts/max_pages must be positive; backoff nonnegative")
    records = []
    for page in range(1, max_pages + 1):
        url = base_url.rstrip('/') + '/orders?' + urlencode({'page': page})
        for attempt in range(attempts):
            try:
                with urlopen(url, timeout=timeout) as response:
                    payload = json.load(response)
                break
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                # Client errors (except rate limiting) usually cannot heal by retrying.
                retryable = not isinstance(exc, HTTPError) or exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt == attempts - 1:
                    raise
                delay = backoff * (2 ** attempt)
                LOG.warning("Request failed (%s); retry %s/%s in %.2fs", exc, attempt + 2, attempts, delay)
                time.sleep(delay)
        if not isinstance(payload, dict) or not isinstance(payload.get('items'), list) or 'next_page' not in payload:
            raise ValueError("API response must contain an items list and next_page")
        records.extend(payload['items'])
        next_page = payload['next_page']
        if next_page is None:
            return records
        if type(next_page) is not int or next_page != page + 1:
            raise ValueError("API next_page must be the next integer page or null")
    raise ValueError("API exceeded max_pages; refusing incomplete extraction")
