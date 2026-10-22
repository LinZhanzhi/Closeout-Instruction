"""Eligibility filtering, per-row account routing, and prefix-based aggregation.

Pipeline, in order (see README "How the pipeline works" for the full rationale):
  1. eligibility filter   - member in {400, 303} and T+1 == '否' (a plain scope filter,
                             not an exception: other members/T+1 values are simply not
                             part of today's batch).
  2. per-row routing      - resolve every raw closeout row to a broker account BEFORE
                             aggregating, using its own trade source. This is the fix for
                             the legacy bug where mixed electronic/manual rows for the same
                             customer/contract got merged and then routed using whichever
                             row happened to survive the merge.
  3. prefix aggregation   - group by account_prefix (first 3 chars of 资金账号) + market +
                             contract + contract type + member, per the new business
                             requirement that ABC1/ABC2/ABC3-style sub-accounts combine.
                             The resolved destination account is folded into the grouping
                             key as well: it is a deterministic function of the other
                             fields, but keeping it explicit guarantees rows that (correctly)
                             routed to different accounts are never summed together.
"""
from __future__ import annotations

from dataclasses import dataclass

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
    COL_FILLED_SOURCE,
    COL_FILLED_T1,
    CONTRACT_TYPE_OPTION,
    MEMBER_OCBC,
    MEMBER_PHILLIP_NOVA,
    T1_ELIGIBLE,
)
from src.mapping import split_contract
from src.routing import RoutingResult, classify_source, route_ocbc, route_pn

MEMBER_TO_BROKER = {MEMBER_PHILLIP_NOVA: "pn", MEMBER_OCBC: "ocbc"}


@dataclass(frozen=True)
class RoutedRow:
    exec_id: str
    account: str
    account_prefix: str
    exchange: str
    contract: str
    contract_product: str
    contract_period: str
    contract_type: str
    member: str
    source: str
    qty: float
    broker: str
    destination: str
    instruction_required: bool
    reason: str


def filter_eligible(enriched_closeout: pd.DataFrame) -> pd.DataFrame:
    """Section 3.2: member in {400, 303} and T+1 == '否'. Not an exception - just scope."""
    member_ok = enriched_closeout[COL_CLOSEOUT_MEMBER].isin(MEMBER_TO_BROKER)
    t1_ok = enriched_closeout[COL_FILLED_T1] == T1_ELIGIBLE
    return enriched_closeout[member_ok & t1_ok]


def route_eligible_rows(
    eligible: pd.DataFrame,
    config: dict,
    exceptions: ExceptionCollector,
) -> list[RoutedRow]:
    electronic_sources = config["electronic_sources"]
    manual_sources = config["manual_sources"]
    pn_routing = config["pn_routing"]
    ocbc_source_rules = config["ocbc_source_rules"]
    ocbc_prefix_overrides = config["ocbc_prefix_overrides"]

    routed: list[RoutedRow] = []

    for _, row in eligible.iterrows():
        account = row[COL_CLOSEOUT_ACCOUNT] or ""
        if not account.strip():
            exceptions.add(
                category="blank_account",
                detail="资金账号 is blank; cannot determine customer prefix or routing.",
                row=row,
            )
            continue

        split = split_contract(row[COL_CLOSEOUT_CONTRACT])
        if split is None:
            exceptions.add(
                category="missing_product_mapping",
                detail=(
                    f"Contract '{row[COL_CLOSEOUT_CONTRACT]}' does not split into exactly "
                    "'PRODUCT PERIOD' - cannot resolve product/month."
                ),
                row=row,
            )
            continue
        contract_product, contract_period = split

        contract_type = "option" if row[COL_CLOSEOUT_TYPE] == CONTRACT_TYPE_OPTION else "futures"
        source_category = classify_source(row[COL_FILLED_SOURCE], electronic_sources, manual_sources)

        fields = {
            "account_prefix": account[:3],
            "exchange": row[COL_CLOSEOUT_EXCHANGE],
            "contract_product": contract_product,
            "contract_type": contract_type,
            "source_category": source_category,
            "internal_account": account,
        }

        member = row[COL_CLOSEOUT_MEMBER]
        broker = MEMBER_TO_BROKER[member]
        result: RoutingResult
        if broker == "pn":
            result = route_pn(fields, pn_routing)
        else:
            result = route_ocbc(fields, ocbc_source_rules, ocbc_prefix_overrides)

        if result.is_exception:
            exceptions.add(
                category=result.exception_category,
                detail=f"{result.reason} (source={row[COL_FILLED_SOURCE]!r}).",
                row=row,
            )
            continue

        routed.append(
            RoutedRow(
                exec_id=row[COL_CLOSEOUT_EXEC_ID],
                account=account,
                account_prefix=account[:3],
                exchange=row[COL_CLOSEOUT_EXCHANGE],
                contract=row[COL_CLOSEOUT_CONTRACT],
                contract_product=contract_product,
                contract_period=contract_period,
                contract_type=contract_type,
                member=member,
                source=row[COL_FILLED_SOURCE],
                qty=float(row[COL_CLOSEOUT_QTY]),
                broker=broker,
                destination=result.destination,
                instruction_required=bool(result.instruction_required),
                reason=result.reason,
            )
        )

    return routed


GROUP_KEY = (
    "account_prefix",
    "exchange",
    "contract",
    "contract_type",
    "member",
    "destination",
)


def aggregate_routed_rows(routed: list[RoutedRow]) -> pd.DataFrame:
    if not routed:
        return pd.DataFrame(
            columns=[
                *GROUP_KEY,
                "account",
                "contract_product",
                "contract_period",
                "source",
                "broker",
                "instruction_required",
                "reason",
                "qty",
                "source_ids",
            ]
        )

    df = pd.DataFrame([r.__dict__ for r in routed])

    grouped = df.groupby(list(GROUP_KEY), as_index=False, sort=False).agg(
        account=("account", "first"),
        contract_product=("contract_product", "first"),
        contract_period=("contract_period", "first"),
        source=("source", "first"),
        broker=("broker", "first"),
        instruction_required=("instruction_required", "first"),
        reason=("reason", "first"),
        qty=("qty", "sum"),
        source_ids=("exec_id", lambda s: "|".join(s.astype(str))),
    )
    return grouped
