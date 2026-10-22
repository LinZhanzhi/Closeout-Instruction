import pandas as pd

from src.exceptions import ExceptionCollector
from src.io import (
    COL_CLOSEOUT_ACCOUNT,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_MEMBER,
    COL_CLOSEOUT_QTY,
    COL_CLOSEOUT_TYPE,
    COL_FILLED_EXEC_ID,
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
)
from src.join import enrich_closeout


def make_closeout(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def make_filled(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def closeout_row(exec_id="EX1", member="400", account="ABC1DEFG", exchange="SGX", contract="UC 2609", qty=1.0):
    return {
        COL_CLOSEOUT_ACCOUNT: account,
        COL_CLOSEOUT_EXCHANGE: exchange,
        COL_CLOSEOUT_CONTRACT: contract,
        COL_CLOSEOUT_QTY: qty,
        COL_CLOSEOUT_TYPE: "期货",
        COL_CLOSEOUT_EXEC_ID: exec_id,
        COL_CLOSEOUT_MEMBER: member,
    }


def filled_row(exec_id="EX1", t1="否", source="程式单"):
    return {COL_FILLED_EXEC_ID: exec_id, COL_FILLED_T1: t1, COL_FILLED_SOURCE: source}


def test_matched_row_copies_t1_and_source():
    closeout = make_closeout([closeout_row(exec_id="EX1")])
    filled = make_filled([filled_row(exec_id="EX1", t1="否", source="程式单")])
    exceptions = ExceptionCollector()

    result = enrich_closeout(closeout, filled, exceptions)

    assert result.iloc[0][COL_FILLED_T1] == "否"
    assert result.iloc[0][COL_FILLED_SOURCE] == "程式单"
    assert len(exceptions) == 0


def test_unmatched_execution_is_reported_and_left_blank():
    closeout = make_closeout([closeout_row(exec_id="MISSING")])
    filled = make_filled([filled_row(exec_id="EX1")])
    exceptions = ExceptionCollector()

    result = enrich_closeout(closeout, filled, exceptions)

    assert pd.isna(result.iloc[0][COL_FILLED_T1])
    df = exceptions.to_dataframe()
    assert len(df) == 1
    assert df.iloc[0]["category"] == "unmatched"


def test_duplicate_execution_id_in_filled_is_reported_and_not_guessed():
    closeout = make_closeout([closeout_row(exec_id="DUP")])
    filled = make_filled([filled_row(exec_id="DUP", t1="否", source="程式单"), filled_row(exec_id="DUP", t1="是", source="人工单")])
    exceptions = ExceptionCollector()

    result = enrich_closeout(closeout, filled, exceptions)

    assert pd.isna(result.iloc[0][COL_FILLED_T1])
    df = exceptions.to_dataframe()
    assert len(df) == 1
    assert df.iloc[0]["category"] == "duplicate_execution_id"


def test_out_of_scope_member_is_not_looked_up_and_not_flagged():
    # member 606 is not Phillip Nova (400) or OCBC (303): out of scope, not an error.
    closeout = make_closeout([closeout_row(exec_id="EX1", member="606")])
    filled = make_filled([filled_row(exec_id="EX1", t1="否", source="程式单")])
    exceptions = ExceptionCollector()

    result = enrich_closeout(closeout, filled, exceptions)

    assert pd.isna(result.iloc[0][COL_FILLED_T1])
    assert len(exceptions) == 0
