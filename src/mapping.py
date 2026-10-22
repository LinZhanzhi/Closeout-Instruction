"""Exchange / product / contract-month code conversion (Esunny -> PN or OCBC).

Mirrors the legacy `data` sheet lookup and `trans_to_phillips_code` month routine, but
returns None (never a blank string masquerading as a valid code) when a mapping is missing,
so the caller can raise a proper exception instead of exporting a blank field silently.
"""
from __future__ import annotations

from typing import Literal

Broker = Literal["pn", "ocbc"]


def convert_exchange(es_exchange: str, broker: Broker, exchange_map: dict) -> str | None:
    entry = exchange_map.get(es_exchange)
    if entry is None:
        return None
    return entry.get(broker)


def convert_product(es_product: str, broker: Broker, product_map: dict) -> str | None:
    entry = product_map.get(es_product)
    if entry is None:
        return None
    return entry.get(broker)


def split_contract(contract: str) -> tuple[str, str] | None:
    """Split 'PRODUCT PERIOD' (e.g. 'UC 2608', 'GC 2609C4500') the way the VBA does: on
    the first space, taking exactly two tokens. Returns None if that shape doesn't hold."""
    parts = contract.split()
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def convert_month(period: str, broker: Broker, month_letters: list[str]) -> str | None:
    """period's first 4 characters must be YYMM; anything after (a day-of-month, or an
    option's C/P + strike) is ignored, exactly like the legacy routine. Returns PN's
    letter+YYYY (e.g. 'U2026') or OCBC's YYYYMM (e.g. '202609'); None if YY/MM don't parse.
    """
    if len(period) < 4 or not period[:4].isdigit():
        return None
    yy, mm = period[0:2], period[2:4]
    month_index = int(mm) - 1
    if not (0 <= month_index <= 11):
        return None

    if broker == "pn":
        return f"{month_letters[month_index]}20{yy}"
    return f"20{yy}{mm}"
