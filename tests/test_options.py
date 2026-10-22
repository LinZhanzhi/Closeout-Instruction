import pytest

from src.options import parse_option_period


@pytest.mark.parametrize(
    "period,call_put,strike",
    [
        ("2609C4500", "C", 4500.0),
        ("2608P24400", "P", 24400.0),
        ("2610P8000", "P", 8000.0),
    ],
)
def test_parse_option_period_success(period, call_put, strike):
    parsed = parse_option_period(period)
    assert parsed is not None
    assert parsed.call_put == call_put
    assert parsed.strike == strike


@pytest.mark.parametrize("period", ["2609", "2609X4500", "abcdC123", "2609C", ""])
def test_parse_option_period_failure(period):
    assert parse_option_period(period) is None
