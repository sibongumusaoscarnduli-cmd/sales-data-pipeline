"""Pure validation: return a clean row or raise ValueError with a useful reason."""
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS = ('line_id', 'order_id', 'sold_on', 'product', 'quantity', 'unit_price_cents', 'currency')


def clean_record(raw):
    if not isinstance(raw, dict):
        raise ValueError("record must be a JSON object")
    row = {}
    for key in ('line_id', 'order_id', 'product'):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(key + " must be nonempty text")
        row[key] = value.strip()
    day = raw.get('sold_on')
    try:
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("sold_on must be a valid YYYY-MM-DD date") from None
    row['sold_on'] = day
    quantity = raw.get('quantity')
    if type(quantity) is not int or not 1 <= quantity <= 1000000:
        raise ValueError("quantity must be an integer between 1 and 1000000")
    row['quantity'] = quantity
    # The API uses decimal strings, avoiding binary floating-point money errors.
    price = raw.get('unit_price')
    if not isinstance(price, str):
        raise ValueError("unit_price must be a decimal string")
    try:
        amount = Decimal(price.strip())
        if not amount.is_finite() or not 0 <= amount <= 1000000:
            raise ValueError()
        cents = amount * 100
        if cents != cents.to_integral_value():
            raise ValueError()
        row['unit_price_cents'] = int(cents)
    except (InvalidOperation, ValueError):
        raise ValueError("unit_price must be nonnegative, <= 1000000, with at most two decimal places") from None
    currency = raw.get('currency')
    if not isinstance(currency, str) or currency.strip().upper() != 'USD':
        raise ValueError("currency must be USD; currencies are never silently mixed")
    row['currency'] = 'USD'
    return row
