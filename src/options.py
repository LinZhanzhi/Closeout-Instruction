"""Parse Call/Put and strike out of an option's contract period token.

Esunny encodes an option period as YYMM + C|P + strike, e.g. '2609C4500' (Call, 4500) or
'2608P24400' (Put, 24400). The legacy macro never parsed this - operators filled Call_Put
and Strike_Price in manually. This is new logic, so a row we can't parse is reported as an
exception rather than exported half-complete.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_OPTION_PERIOD_RE = re.compile(r"^\d{4}([CP])(\d+(?:\.\d+)?)$")


@dataclass(frozen=True)
class ParsedOption:
    call_put: str
    strike: float


def parse_option_period(period: str) -> ParsedOption | None:
    match = _OPTION_PERIOD_RE.match(period)
    if not match:
        return None
    call_put, strike = match.groups()
    return ParsedOption(call_put=call_put, strike=float(strike))
