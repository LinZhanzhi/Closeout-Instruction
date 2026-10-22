"""Collects every record we could not confidently turn into a broker instruction.

Nothing gets dropped silently: every row excluded anywhere in the pipeline for a reason
other than plain out-of-scope filtering (wrong member number, T+1 not yet due) is recorded
here with a category and a human-readable detail string.
"""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from src.io import (
    COL_CLOSEOUT_ACCOUNT,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_MEMBER,
    COL_CLOSEOUT_TYPE,
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
)

CATEGORIES = (
    "unmatched",
    "duplicate_execution_id",
    "unknown_source",
    "missing_exchange_mapping",
    "missing_product_mapping",
    "blank_account",
    "option_parse_failed",
    "no_destination",
)

EXCEPTION_COLUMNS = [
    "category",
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_ACCOUNT,
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_TYPE,
    COL_CLOSEOUT_MEMBER,
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
    "detail",
]

_ROW_FIELDS = [
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_ACCOUNT,
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_TYPE,
    COL_CLOSEOUT_MEMBER,
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
]


class ExceptionCollector:
    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []

    def add(
        self,
        category: str,
        detail: str,
        row: Mapping[str, Any] | pd.Series | None = None,
        **field_overrides: Any,
    ) -> None:
        if category not in CATEGORIES:
            raise ValueError(f"Unknown exception category: {category!r}")

        record: dict[str, Any] = {"category": category, "detail": detail}
        for field in _ROW_FIELDS:
            record[field] = row.get(field) if row is not None else None
        record.update(field_overrides)
        self._records.append(record)

    def __len__(self) -> int:
        return len(self._records)

    def to_dataframe(self) -> pd.DataFrame:
        if not self._records:
            return pd.DataFrame(columns=EXCEPTION_COLUMNS)
        return pd.DataFrame(self._records, columns=EXCEPTION_COLUMNS)
