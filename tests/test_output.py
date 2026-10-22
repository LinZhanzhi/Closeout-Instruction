import pandas as pd

from src.exceptions import ExceptionCollector
from src.output import build_ocbc_sheet, build_pn_sheet, build_summary, finalize_summary


def group_row(**overrides):
    row = {
        "account_prefix": "ABC",
        "exchange": "SGX",
        "contract": "UC 2609",
        "contract_type": "futures",
        "member": "400",
        "destination": "BNS8001",
        "account": "ABC1DEFG",
        "contract_product": "UC",
        "contract_period": "2609",
        "source": "程式单",
        "broker": "pn",
        "instruction_required": True,
        "reason": "Electronic-source futures",
        "qty": 10.0,
        "source_ids": "E1|E2",
    }
    row.update(overrides)
    return row


def test_instruction_required_row_is_in_summary_and_broker_sheet(config):
    aggregated = pd.DataFrame([group_row()])
    exceptions = ExceptionCollector()

    summary = build_summary(aggregated, config, exceptions)
    pn_sheet = build_pn_sheet(summary)
    ocbc_sheet = build_ocbc_sheet(summary)
    final = finalize_summary(summary)

    assert len(final) == 1
    assert final.iloc[0]["exclusion_reason"] == ""
    assert len(pn_sheet) == 1
    assert len(ocbc_sheet) == 0
    assert len(exceptions) == 0


def test_no_closeout_row_stays_in_summary_but_excluded_from_pn_sheet(config):
    # BNS8888 (DUK/SUL routes) is configured with closeout_method "none".
    aggregated = pd.DataFrame([group_row(destination="BNS8888", instruction_required=False, reason="Customer prefix DUK")])
    exceptions = ExceptionCollector()

    summary = build_summary(aggregated, config, exceptions)
    pn_sheet = build_pn_sheet(summary)
    final = finalize_summary(summary)

    assert len(final) == 1  # still present for audit
    assert final.iloc[0]["exclusion_reason"] == "No need close-out"
    assert len(pn_sheet) == 0  # excluded from the outbound instruction file


def test_automatic_close_ocbc_row_stays_in_summary_but_excluded_from_ocbc_sheet(config):
    aggregated = pd.DataFrame(
        [
            group_row(
                broker="ocbc",
                member="303",
                destination="A2123N-B2",
                instruction_required=False,
                reason="Electronic, exact internal account 232P or 239P",
            )
        ]
    )
    exceptions = ExceptionCollector()

    summary = build_summary(aggregated, config, exceptions)
    ocbc_sheet = build_ocbc_sheet(summary)
    final = finalize_summary(summary)

    assert len(final) == 1
    assert final.iloc[0]["exclusion_reason"] == "Auto close, no need email"
    assert len(ocbc_sheet) == 0


def test_missing_exchange_mapping_is_reported_and_excluded(config):
    aggregated = pd.DataFrame([group_row(exchange="NOWHERE")])
    exceptions = ExceptionCollector()

    summary = build_summary(aggregated, config, exceptions)
    pn_sheet = build_pn_sheet(summary)
    final = finalize_summary(summary)

    assert len(final) == 1
    assert final.iloc[0]["exclusion_reason"] == "missing_exchange_mapping"
    assert len(pn_sheet) == 0
    exc_df = exceptions.to_dataframe()
    assert list(exc_df["category"]) == ["missing_exchange_mapping"]


def test_option_row_populates_call_put_and_strike(config):
    aggregated = pd.DataFrame(
        [
            group_row(
                broker="ocbc",
                member="303",
                exchange="HKEX",
                contract="HSI 2608P24400",
                contract_type="option",
                contract_product="HSI",
                contract_period="2608P24400",
                destination="A2123N-B3",
            )
        ]
    )
    exceptions = ExceptionCollector()

    summary = build_summary(aggregated, config, exceptions)
    ocbc_sheet = build_ocbc_sheet(summary)
    final = finalize_summary(summary)

    assert final.iloc[0]["Call_Put"] == "P"
    assert final.iloc[0]["Strike_Price"] == 24400.0
    assert len(ocbc_sheet) == 1
    assert ocbc_sheet.iloc[0]["Options Type"] == "Put"
    assert ocbc_sheet.iloc[0]["Strike Price"] == 24400.0
    assert len(exceptions) == 0


def pxn_row(**overrides):
    row = dict(
        broker="ocbc",
        member="303",
        contract="PXN 2701",
        contract_product="PXN",
        contract_period="2701",
        destination="A2123N-B1",
        reason="Other manual",
        source="人工单",
    )
    row.update(overrides)
    return group_row(**row)


def test_pxn_ocbc_ticker_matches_instruction_actually_sent_to_ocbc(config):
    # The 26 Aug instruction sent to OCBC was A2123N-B1 / F-XSIM-PXN-202701 / 10 lots.
    aggregated = pd.DataFrame([pxn_row()])
    exceptions = ExceptionCollector()

    ocbc_sheet = build_ocbc_sheet(build_summary(aggregated, config, exceptions))

    assert len(exceptions) == 0
    assert ocbc_sheet.iloc[0]["*Trading Account Number"] == "A2123N-B1"
    assert ocbc_sheet.iloc[0]["*Falcon Contract Ticker"] == "F-XSIM-PXN-202701"


def test_pxn_no_closeout_row_no_longer_raises_mapping_exception(config):
    # Operations' case: TOR / PXN Jan 2027 / 10 lots -> A2123N-B5, no closeout instruction.
    aggregated = pd.DataFrame(
        [pxn_row(account_prefix="TOR", account="TOR1XXXX", destination="A2123N-B5", instruction_required=False)]
    )
    exceptions = ExceptionCollector()

    final = finalize_summary(build_summary(aggregated, config, exceptions))

    assert len(exceptions) == 0
    assert final.iloc[0]["Com_cd"] == "PXN"
    assert final.iloc[0]["exclusion_reason"] == "No need close-out"


def test_pxn_on_phillip_nova_is_flagged_until_pn_code_is_confirmed(config):
    aggregated = pd.DataFrame([pxn_row(broker="pn", member="400", destination="BNS8002")])
    exceptions = ExceptionCollector()

    pn_sheet = build_pn_sheet(build_summary(aggregated, config, exceptions))

    assert len(pn_sheet) == 0
    assert list(exceptions.to_dataframe()["category"]) == ["missing_product_mapping"]


def test_option_parse_failure_is_reported_and_excluded(config):
    aggregated = pd.DataFrame(
        [
            group_row(
                contract="UC 2609Q4500",  # 'Q' is not a valid call/put letter
                contract_type="option",
                contract_product="UC",
                contract_period="2609Q4500",
            )
        ]
    )
    exceptions = ExceptionCollector()

    summary = build_summary(aggregated, config, exceptions)
    pn_sheet = build_pn_sheet(summary)
    final = finalize_summary(summary)

    assert final.iloc[0]["exclusion_reason"] == "option_parse_failed"
    assert pd.isna(final.iloc[0]["Call_Put"])
    assert len(pn_sheet) == 0
    exc_df = exceptions.to_dataframe()
    assert list(exc_df["category"]) == ["option_parse_failed"]
