import pandas as pd

from src.aggregate import aggregate_routed_rows, filter_eligible, route_eligible_rows
from src.exceptions import ExceptionCollector
from src.io import (
    COL_CLOSEOUT_ACCOUNT,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_MEMBER,
    COL_CLOSEOUT_QTY,
    COL_CLOSEOUT_TYPE,
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
)


def enriched_row(exec_id, account, exchange="SGX", contract="UC 2609", qty=1.0, member="400", t1="否", source="程式单", contract_type="期货"):
    return {
        COL_CLOSEOUT_ACCOUNT: account,
        COL_CLOSEOUT_EXCHANGE: exchange,
        COL_CLOSEOUT_CONTRACT: contract,
        COL_CLOSEOUT_QTY: qty,
        COL_CLOSEOUT_TYPE: contract_type,
        COL_CLOSEOUT_EXEC_ID: exec_id,
        COL_CLOSEOUT_MEMBER: member,
        COL_FILLED_T1: t1,
        COL_FILLED_SOURCE: source,
    }


def test_filter_eligible_keeps_only_400_303_with_t1_no(config):
    df = pd.DataFrame(
        [
            enriched_row("E1", "ABC1DEFG", member="400", t1="否"),
            enriched_row("E2", "ABC1DEFG", member="400", t1="是"),  # wrong T+1
            enriched_row("E3", "ABC1DEFG", member="606", t1="否"),  # wrong member
            enriched_row("E4", "ABC1DEFG", member="303", t1="否"),
        ]
    )
    result = filter_eligible(df)
    assert set(result[COL_CLOSEOUT_EXEC_ID]) == {"E1", "E4"}


def test_prefix_grouping_merges_same_prefix_accounts(config):
    # ABC1DEFG / ABC2DEFG / ABC3DEFG all become prefix "ABC" and must combine, per the new
    # business requirement (section 3.4 of the spec).
    df = pd.DataFrame(
        [
            enriched_row("E1", "ABC1DEFG", qty=1, source="程式单"),
            enriched_row("E2", "ABC2DEFG", qty=2, source="程式单"),
            enriched_row("E3", "ABC3DEFG", qty=3, source="程式单"),
        ]
    )
    eligible = filter_eligible(df)
    exceptions = ExceptionCollector()
    routed = route_eligible_rows(eligible, config, exceptions)
    aggregated = aggregate_routed_rows(routed)

    assert len(exceptions) == 0
    assert len(aggregated) == 1
    row = aggregated.iloc[0]
    assert row["account_prefix"] == "ABC"
    assert row["qty"] == 6
    assert set(row["source_ids"].split("|")) == {"E1", "E2", "E3"}


def test_different_prefixes_do_not_merge(config):
    df = pd.DataFrame(
        [
            enriched_row("E1", "ABC1DEFG", qty=1, source="程式单"),
            enriched_row("E2", "XYZ1DEFG", qty=2, source="程式单"),
        ]
    )
    eligible = filter_eligible(df)
    exceptions = ExceptionCollector()
    routed = route_eligible_rows(eligible, config, exceptions)
    aggregated = aggregate_routed_rows(routed)

    assert len(aggregated) == 2
    assert set(aggregated["account_prefix"]) == {"ABC", "XYZ"}


def test_same_prefix_mixed_source_routes_separately_not_merged(config):
    # An electronic and a manual order for the same customer/contract must route to
    # different PN accounts (BNS8001 vs BNS8002) and therefore cannot be summed together,
    # even though account_prefix/market/contract/type/member all match. This is the fix for
    # the legacy bug where the "surviving" row's source silently decided the whole group's
    # routing (see README / developer handover).
    df = pd.DataFrame(
        [
            enriched_row("E1", "ABC1DEFG", qty=1, source="程式单"),  # electronic -> BNS8001
            enriched_row("E2", "ABC2DEFG", qty=2, source="人工单"),  # manual -> BNS8002
        ]
    )
    eligible = filter_eligible(df)
    exceptions = ExceptionCollector()
    routed = route_eligible_rows(eligible, config, exceptions)
    aggregated = aggregate_routed_rows(routed)

    assert len(aggregated) == 2
    destinations = dict(zip(aggregated["destination"], aggregated["qty"]))
    assert destinations == {"BNS8001": 1, "BNS8002": 2}


def test_blank_account_is_reported_and_excluded(config):
    df = pd.DataFrame([enriched_row("E1", "   ")])
    eligible = filter_eligible(df)
    exceptions = ExceptionCollector()
    routed = route_eligible_rows(eligible, config, exceptions)

    assert routed == []
    df_exc = exceptions.to_dataframe()
    assert len(df_exc) == 1
    assert df_exc.iloc[0]["category"] == "blank_account"
