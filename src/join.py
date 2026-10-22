"""Enrich closeP rows with the closing execution's T+1 flag and trade source.

Only closeP rows whose clearing member is 400 (Phillip Nova) or 303 (OCBC) are looked up
against `filled` - this program only ever produces instructions for those two brokers, so a
closeout under some other member number (e.g. an inter-member 606/INE code) is out of scope,
not an error, and is left untouched (T+1/成交来源 stay blank). This mirrors the legacy VBA's
own `If member = 303 Or 400 ... Else N/A` branch. See README "Design decisions".

Within the 400/303 scope, every row must resolve to exactly one filled execution:
- no matching execution id in `filled`      -> exception "unmatched"
- the execution id appears more than once
  in `filled` (ambiguous, cannot pick one)  -> exception "duplicate_execution_id"
Rows in either case are left without T+1/成交来源 and will naturally fail the T+1 eligibility
filter downstream, but they are still reported explicitly rather than silently dropped.
"""
from __future__ import annotations

import pandas as pd

from src.io import (
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_MEMBER,
    COL_FILLED_EXEC_ID,
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
    MEMBER_OCBC,
    MEMBER_PHILLIP_NOVA,
)
from src.exceptions import ExceptionCollector

IN_SCOPE_MEMBERS = {MEMBER_PHILLIP_NOVA, MEMBER_OCBC}


def enrich_closeout(
    closeout: pd.DataFrame,
    filled: pd.DataFrame,
    exceptions: ExceptionCollector,
) -> pd.DataFrame:
    result = closeout.copy()
    result[COL_FILLED_T1] = pd.NA
    result[COL_FILLED_SOURCE] = pd.NA

    exec_id_counts = filled[COL_FILLED_EXEC_ID].value_counts()
    unique_lookup = (
        filled[filled[COL_FILLED_EXEC_ID].map(exec_id_counts) == 1]
        .set_index(COL_FILLED_EXEC_ID)[[COL_FILLED_T1, COL_FILLED_SOURCE]]
    )

    in_scope = result[COL_CLOSEOUT_MEMBER].isin(IN_SCOPE_MEMBERS)

    for idx, row in result[in_scope].iterrows():
        exec_id = row[COL_CLOSEOUT_EXEC_ID]
        occurrences = exec_id_counts.get(exec_id, 0)

        if occurrences == 0:
            exceptions.add(
                category="unmatched",
                row=row,
                detail=f"No filled row found for closing execution id '{exec_id}'.",
            )
        elif occurrences > 1:
            exceptions.add(
                category="duplicate_execution_id",
                row=row,
                detail=(
                    f"Execution id '{exec_id}' appears {occurrences} times in filled; "
                    "cannot determine which T+1/成交来源 to use."
                ),
            )
        else:
            result.at[idx, COL_FILLED_T1] = unique_lookup.at[exec_id, COL_FILLED_T1]
            result.at[idx, COL_FILLED_SOURCE] = unique_lookup.at[exec_id, COL_FILLED_SOURCE]

    return result
