import pytest

from src.mapping import convert_exchange, convert_month, convert_product, split_contract

MONTH_LETTERS = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]


@pytest.mark.parametrize(
    "period,broker,expected",
    [
        ("2609", "pn", "U2026"),
        ("2609", "ocbc", "202609"),
        ("2601", "pn", "F2026"),
        ("2612", "pn", "Z2026"),
        ("260819", "pn", "Q2026"),  # LME-style day contract: only first 4 chars (YYMM) matter
        ("2608P24400", "pn", "Q2026"),  # option period: YYMM prefix still parses
        ("2608P24400", "ocbc", "202608"),
    ],
)
def test_convert_month(period, broker, expected):
    assert convert_month(period, broker, MONTH_LETTERS) == expected


@pytest.mark.parametrize("period", ["13", "26", "2613", "260099", "abcd"])
def test_convert_month_returns_none_for_invalid_month(period):
    assert convert_month(period, "pn", MONTH_LETTERS) is None


def test_convert_exchange_known_and_unknown():
    exchange_map = {"SGX": {"pn": "SIMEX", "ocbc": "XSIM"}, "COMEX": {"pn": None, "ocbc": "XCEC"}}
    assert convert_exchange("SGX", "pn", exchange_map) == "SIMEX"
    assert convert_exchange("SGX", "ocbc", exchange_map) == "XSIM"
    assert convert_exchange("COMEX", "pn", exchange_map) is None  # known exchange, blank PN mapping
    assert convert_exchange("NOPE", "pn", exchange_map) is None  # unknown exchange entirely


def test_convert_product_known_and_unknown():
    product_map = {"UC": {"pn": "UC", "ocbc": "UC"}, "CPO": {"pn": "PO", "ocbc": "FCPO"}}
    assert convert_product("CPO", "pn", product_map) == "PO"
    assert convert_product("CPO", "ocbc", product_map) == "FCPO"
    assert convert_product("NOPE", "pn", product_map) is None


@pytest.mark.parametrize(
    "contract,expected",
    [
        ("UC 2608", ("UC", "2608")),
        ("GC 2609C4500", ("GC", "2609C4500")),
        ("CA 260819", ("CA", "260819")),
        ("NOSPACE", None),
        ("TOO MANY TOKENS", None),
    ],
)
def test_split_contract(contract, expected):
    assert split_contract(contract) == expected
