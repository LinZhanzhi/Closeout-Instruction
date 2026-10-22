"""Reading Esunny CSV exports and writing the reviewed Excel output."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# --- filled.csv (Esunny execution export) ---
COL_FILLED_EXEC_ID = "成交号"
COL_FILLED_T1 = "T+1"
COL_FILLED_SOURCE = "成交来源"

FILLED_COLUMNS = [COL_FILLED_EXEC_ID, COL_FILLED_T1, COL_FILLED_SOURCE]

# --- closeP.csv (Esunny closeout export) ---
COL_CLOSEOUT_ACCOUNT = "资金账号"
COL_CLOSEOUT_EXCHANGE = "市场"
COL_CLOSEOUT_CONTRACT = "合约"
COL_CLOSEOUT_QTY = "数量"
COL_CLOSEOUT_TYPE = "合约类型"
COL_CLOSEOUT_EXEC_ID = "平仓成交号"
COL_CLOSEOUT_MEMBER = "平仓会员号"

CLOSEOUT_COLUMNS = [
    COL_CLOSEOUT_ACCOUNT,
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_QTY,
    COL_CLOSEOUT_TYPE,
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_MEMBER,
]

CONTRACT_TYPE_FUTURES = "期货"
CONTRACT_TYPE_OPTION = "期权"

MEMBER_PHILLIP_NOVA = "400"
MEMBER_OCBC = "303"

T1_ELIGIBLE = "否"


def _strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Esunny exports pad text fields with trailing spaces; strip them like the VBA does."""
    # Every column is text here (read with dtype=str). Do not test for dtype == object:
    # pandas 3 gives text columns a "str" dtype, and skipping the strip leaves "400   ",
    # which matches no member number and silently produces an empty workbook.
    for col in df.columns:
        df[col] = df[col].str.strip()
    return df


# UTF-8 goes first: GBK can "successfully" decode UTF-8 bytes into garbage, but UTF-8
# reliably rejects GBK Chinese text. The header check below catches any remaining mis-decode.
DEFAULT_ENCODINGS = ("utf-8-sig", "gbk")


def _read_csv(path: str | Path, encodings: list[str] | tuple[str, ...], required_columns: list[str], label: str) -> pd.DataFrame:
    attempts = []
    for encoding in encodings:
        try:
            # keep_default_na=False: an empty cell stays "" and codes such as "NA" stay text,
            # instead of both turning into a missing-value marker.
            df = pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            attempts.append(f"{encoding}: not valid {encoding} text")
            continue
        df.columns = df.columns.str.strip()
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            attempts.append(f"{encoding}: decoded, but missing columns {missing}")
            continue
        return _strip_whitespace(df)
    raise ValueError(f"Could not read {label} export '{path}'. Tried: " + "; ".join(attempts))


def read_filled(path: str | Path, encodings: list[str] | tuple[str, ...] = DEFAULT_ENCODINGS) -> pd.DataFrame:
    df = _read_csv(path, encodings, FILLED_COLUMNS, "filled")
    return df[FILLED_COLUMNS]


def read_closeout(path: str | Path, encodings: list[str] | tuple[str, ...] = DEFAULT_ENCODINGS) -> pd.DataFrame:
    df = _read_csv(path, encodings, CLOSEOUT_COLUMNS, "closeP")
    df = df[CLOSEOUT_COLUMNS].copy()
    df[COL_CLOSEOUT_QTY] = pd.to_numeric(df[COL_CLOSEOUT_QTY], errors="coerce")
    return df


def write_output(path: str | Path, sheets: dict[str, pd.DataFrame]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
