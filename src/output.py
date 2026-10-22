"""Build the summary / PN / OCBC / trace sheets from aggregated, routed closeout groups."""
from __future__ import annotations

import pandas as pd

from src.exceptions import ExceptionCollector
from src.io import (
    COL_CLOSEOUT_ACCOUNT,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_EXEC_ID,
    COL_CLOSEOUT_MEMBER,
    COL_CLOSEOUT_TYPE,
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
    CONTRACT_TYPE_FUTURES,
    CONTRACT_TYPE_OPTION,
    T1_ELIGIBLE,
)
from src.mapping import convert_exchange, convert_month, convert_product
from src.options import parse_option_period

SUMMARY_COLUMNS = [
    "account_prefix",
    "broker_account",
    "account_type",
    "closeout_method",
    "instruction_required",
    "exclusion_reason",
    COL_CLOSEOUT_EXCHANGE,
    COL_CLOSEOUT_CONTRACT,
    COL_CLOSEOUT_TYPE,
    COL_CLOSEOUT_MEMBER,
    "Com_Type",
    "Exch_cd",
    "Com_cd",
    "Contract_Month",
    "Traded_Qty",
    "Strike_Price",
    "Call_Put",
    "source_ids",
]

PN_COLUMNS = [
    "client_no",
    "Com_Type",
    "Exch_cd",
    "Com_cd",
    "Contract_Month",
    "Strike_Price",
    "Call_Put",
    "Val_Date",
    "Trade_Date_Buy",
    "Trade_Date_Sell",
    "Traded_Qty",
    "Traded_Price_Buy",
    "Traded_Price_Sell",
    "Traded_Premium_Buy",
    "Traded_Premium_Sell",
]

OCBC_COLUMNS = [
    "*Trading Account Number",
    "Sub Account",
    "*Balance Type",
    "Asset Type",
    "Exchange MIC",
    "Product Symbol Type",
    "Product Symbol",
    "Contract Month(YYYYMM/YYYYMMDD)",
    "Options Type",
    "Strike Price",
    "*Falcon Contract Ticker",
    "*Quantity",
    "Buy price",
    "Sell Price",
    "*offset with counterparty",
    "Trade Price Multiplier",
    "Strike Price Multiplier",
]

TRACE_COLUMNS = ["output_sheet", "output_row_index", "account_prefix", "broker_account", "source_ids"]

_OPTIONS_TYPE_WORD = {"C": "Call", "P": "Put"}


def _pseudo_row(group: pd.Series, raw_contract_type: str) -> dict:
    return {
        COL_CLOSEOUT_EXEC_ID: group["source_ids"],
        COL_CLOSEOUT_ACCOUNT: group["account"],
        COL_CLOSEOUT_EXCHANGE: group["exchange"],
        COL_CLOSEOUT_CONTRACT: group["contract"],
        COL_CLOSEOUT_TYPE: raw_contract_type,
        COL_CLOSEOUT_MEMBER: group["member"],
        COL_FILLED_SOURCE: group["source"],
        COL_FILLED_T1: T1_ELIGIBLE,
    }


def build_summary(aggregated: pd.DataFrame, config: dict, exceptions: ExceptionCollector) -> pd.DataFrame:
    exchange_map = config["exchange_map"]
    product_map = config["product_map"]
    month_letters = config["month_letters"]
    account_type_map = config["account_type_map"]
    no_closeout_labels = config["no_closeout_reason_labels"]

    rows = []
    for _, g in aggregated.iterrows():
        broker = g["broker"]
        is_option = g["contract_type"] == "option"
        raw_contract_type = CONTRACT_TYPE_OPTION if is_option else CONTRACT_TYPE_FUTURES
        com_type = "O" if is_option else "F"

        exch_cd = convert_exchange(g["exchange"], broker, exchange_map)
        com_cd = convert_product(g["contract_product"], broker, product_map)
        contract_month = convert_month(g["contract_period"], broker, month_letters)

        call_put = None
        strike_price = None
        option_parsed_ok = True
        if is_option:
            parsed = parse_option_period(g["contract_period"])
            if parsed is None:
                option_parsed_ok = False
            else:
                call_put, strike_price = parsed.call_put, parsed.strike

        pseudo_row = _pseudo_row(g, raw_contract_type)
        if exch_cd is None:
            exceptions.add(
                category="missing_exchange_mapping",
                detail=f"No {broker.upper()} mapping configured for exchange '{g['exchange']}'.",
                row=pseudo_row,
            )
        if com_cd is None or contract_month is None:
            reason = f"product '{g['contract_product']}'" if com_cd is None else f"period '{g['contract_period']}'"
            exceptions.add(
                category="missing_product_mapping",
                detail=f"Could not resolve {broker.upper()} code for {reason}.",
                row=pseudo_row,
            )
        if is_option and not option_parsed_ok:
            exceptions.add(
                category="option_parse_failed",
                detail=f"Could not parse Call/Put and strike from period '{g['contract_period']}'.",
                row=pseudo_row,
            )

        mapping_ok = exch_cd is not None and com_cd is not None and contract_month is not None
        option_ok = (not is_option) or option_parsed_ok
        instruction_required = bool(g["instruction_required"])

        account_meta = account_type_map.get(g["destination"], {})
        account_type = account_meta.get("account_type")
        closeout_method = account_meta.get("closeout_method")

        if not instruction_required:
            exclusion_reason = no_closeout_labels.get(closeout_method, g["reason"])
        elif not mapping_ok:
            exclusion_reason = "missing_exchange_mapping" if exch_cd is None else "missing_product_mapping"
        elif not option_ok:
            exclusion_reason = "option_parse_failed"
        else:
            exclusion_reason = ""

        rows.append(
            {
                "account_prefix": g["account_prefix"],
                "broker_account": g["destination"],
                "account_type": account_type,
                "closeout_method": closeout_method,
                "instruction_required": "Yes" if instruction_required else "No",
                "exclusion_reason": exclusion_reason,
                COL_CLOSEOUT_EXCHANGE: g["exchange"],
                COL_CLOSEOUT_CONTRACT: g["contract"],
                COL_CLOSEOUT_TYPE: raw_contract_type,
                COL_CLOSEOUT_MEMBER: g["member"],
                "Com_Type": com_type,
                "Exch_cd": exch_cd,
                "Com_cd": com_cd,
                "Contract_Month": contract_month,
                "Traded_Qty": g["qty"],
                "Strike_Price": strike_price,
                "Call_Put": call_put,
                "source_ids": g["source_ids"],
                # kept only for build_pn_sheet/build_ocbc_sheet/build_trace below, dropped before export
                "_broker": broker,
                "_include_in_output": instruction_required and mapping_ok and option_ok,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS + ["_broker", "_include_in_output"])
    return df


def build_pn_sheet(summary: pd.DataFrame) -> pd.DataFrame:
    eligible = summary[(summary["_broker"] == "pn") & summary["_include_in_output"]]
    return pd.DataFrame(
        {
            "client_no": eligible["broker_account"],
            "Com_Type": eligible["Com_Type"],
            "Exch_cd": eligible["Exch_cd"],
            "Com_cd": eligible["Com_cd"],
            "Contract_Month": eligible["Contract_Month"],
            "Strike_Price": eligible["Strike_Price"],
            "Call_Put": eligible["Call_Put"],
            "Val_Date": None,
            "Trade_Date_Buy": None,
            "Trade_Date_Sell": None,
            "Traded_Qty": eligible["Traded_Qty"],
            "Traded_Price_Buy": None,
            "Traded_Price_Sell": None,
            "Traded_Premium_Buy": None,
            "Traded_Premium_Sell": None,
        }
    ).reset_index(drop=True)


def build_ocbc_sheet(summary: pd.DataFrame) -> pd.DataFrame:
    eligible = summary[(summary["_broker"] == "ocbc") & summary["_include_in_output"]].reset_index(drop=True)
    tickers = (
        eligible["Com_Type"] + "-" + eligible["Exch_cd"] + "-" + eligible["Com_cd"] + "-" + eligible["Contract_Month"]
    )
    options_type = eligible["Call_Put"].map(lambda cp: _OPTIONS_TYPE_WORD.get(cp))
    return pd.DataFrame(
        {
            "*Trading Account Number": eligible["broker_account"],
            "Sub Account": None,
            "*Balance Type": "Segregated",
            "Asset Type": None,
            "Exchange MIC": None,
            "Product Symbol Type": None,
            "Product Symbol": None,
            "Contract Month(YYYYMM/YYYYMMDD)": None,
            "Options Type": options_type,
            "Strike Price": eligible["Strike_Price"],
            "*Falcon Contract Ticker": tickers,
            "*Quantity": eligible["Traded_Qty"],
            "Buy price": None,
            "Sell Price": None,
            "*offset with counterparty": "Yes",
            "Trade Price Multiplier": None,
            "Strike Price Multiplier": None,
        }
    )


def build_trace(summary: pd.DataFrame, pn_sheet: pd.DataFrame, ocbc_sheet: pd.DataFrame) -> pd.DataFrame:
    pn_source = summary[(summary["_broker"] == "pn") & summary["_include_in_output"]].reset_index(drop=True)
    ocbc_source = summary[(summary["_broker"] == "ocbc") & summary["_include_in_output"]].reset_index(drop=True)

    rows = []
    for i in range(len(pn_sheet)):
        rows.append(
            {
                "output_sheet": "PN",
                "output_row_index": i + 1,
                "account_prefix": pn_source.loc[i, "account_prefix"],
                "broker_account": pn_source.loc[i, "broker_account"],
                "source_ids": pn_source.loc[i, "source_ids"],
            }
        )
    for i in range(len(ocbc_sheet)):
        rows.append(
            {
                "output_sheet": "OCBC",
                "output_row_index": i + 1,
                "account_prefix": ocbc_source.loc[i, "account_prefix"],
                "broker_account": ocbc_source.loc[i, "broker_account"],
                "source_ids": ocbc_source.loc[i, "source_ids"],
            }
        )
    return pd.DataFrame(rows, columns=TRACE_COLUMNS)


def finalize_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """Drop the internal helper columns before this sheet is exported."""
    if summary.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    return summary[SUMMARY_COLUMNS].reset_index(drop=True)
