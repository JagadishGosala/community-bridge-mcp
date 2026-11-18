"""Exact money parsing and formatting (REQ-15, A-10; AC-24, AC-25 at unit level)."""

import pytest

from cb.money import format_cents, parse_amount

# AC-24, verbatim.
AC24_INVALID_STRINGS = ["0", "-5", "10.999", "abc", "1e3", "1000000.01", " 300", "", "٣٠٠"]

# Further strings the REQ-15 regex or range rejects.
REQ15_INVALID_STRINGS = ["0.00", "300.", ".50", "+300", "300 ", "1,000", "10000000", "３００"]


@pytest.mark.parametrize("value", AC24_INVALID_STRINGS + REQ15_INVALID_STRINGS, ids=repr)
def test_invalid_amount_strings_are_rejected(value):
    with pytest.raises(ValueError):
        parse_amount(value)


@pytest.mark.parametrize("value", [300, 300.0, None], ids=repr)
def test_non_string_amounts_are_rejected(value):
    # AC-24: a JSON number 300 is not an amount.
    with pytest.raises(ValueError):
        parse_amount(value)


@pytest.mark.parametrize(
    "value,cents",
    [
        ("0.01", 1),
        ("1000000.00", 100_000_000),
        ("300", 30_000),
        ("300.5", 30_050),
        ("300.00", 30_000),
        ("9700.00", 970_000),
        ("0.10", 10),
    ],
)
def test_valid_amounts_parse_to_exact_integer_cents(value, cents):
    result = parse_amount(value)
    assert type(result) is int
    assert result == cents


@pytest.mark.parametrize(
    "cents,text",
    [
        (1, "0.01"),
        (100_000_000, "1000000.00"),
        (30_000, "300.00"),
        (30_050, "300.50"),
        (0, "0.00"),
        (5, "0.05"),
        (970_000, "9700.00"),
    ],
)
def test_format_cents_gives_exactly_two_decimals(cents, text):
    assert format_cents(cents) == text


@pytest.mark.parametrize(
    "value,text",
    [("0.01", "0.01"), ("1000000.00", "1000000.00"), ("300", "300.00"), ("300.5", "300.50")],
)
def test_ac25_round_trip(value, text):
    assert format_cents(parse_amount(value)) == text
