"""Exact USD amounts as integer cents (REQ-15, A-10, §7). No floating point."""

import re
from decimal import Decimal

# REQ-15. [0-9] matches ASCII digits only; used with fullmatch.
AMOUNT_PATTERN = re.compile(r"[0-9]{1,7}(\.[0-9]{1,2})?")
MIN_CENTS = 1  # 0.01
MAX_CENTS = 100_000_000  # 1,000,000.00


def parse_amount(value: object) -> int:
    """Parse an amount string such as "300.00" to integer cents; ValueError if invalid."""
    if not isinstance(value, str) or AMOUNT_PATTERN.fullmatch(value) is None:
        raise ValueError('amount must be a decimal string such as "300.00" with at most 2 decimals')
    cents = int(Decimal(value) * 100)
    if not MIN_CENTS <= cents <= MAX_CENTS:
        raise ValueError("amount must be between 0.01 and 1000000.00")
    return cents


def format_cents(cents: int) -> str:
    """Integer cents to a decimal string with exactly two decimals, e.g. 970000 -> "9700.00"."""
    return f"{cents // 100}.{cents % 100:02d}"
