"""Config-driven account routing for Phillip Nova (member 400) and OCBC (member 303).

Every rule in config.yaml's pn_routing / ocbc_source_rules / ocbc_prefix_overrides is
evaluated against a plain dict of fields computed for one raw closeout row - routing
happens BEFORE aggregation (see aggregate.py), so an electronic and a manual order for the
same customer/contract can never be silently merged and routed using only one of their
sources, which is the exact bug the developer handover flags in the legacy macro.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RoutingResult:
    destination: str | None
    instruction_required: bool | None
    reason: str
    exception_category: str | None = None

    @property
    def is_exception(self) -> bool:
        return self.exception_category is not None


ROUTING_FIELDS = (
    "account_prefix",
    "exchange",
    "contract_product",
    "contract_type",
    "source_category",
    "internal_account",
)

OPS = {
    "equals": lambda value, target: value == target,
    "in": lambda value, target: value in target,
    "starts_with": lambda value, target: isinstance(value, str) and value.startswith(target),
    "starts_with_any": lambda value, target: isinstance(value, str) and value.startswith(tuple(target)),
}


def _condition_matches(fields: dict[str, Any], condition: dict[str, Any]) -> bool:
    return OPS[condition["op"]](fields.get(condition["field"]), condition["value"])


def _rule_matches(fields: dict[str, Any], rule: dict[str, Any]) -> bool:
    return all(_condition_matches(fields, cond) for cond in rule["all_of"])


def route_pn(fields: dict[str, Any], pn_routing: list[dict[str, Any]]) -> RoutingResult:
    for rule in pn_routing:
        if not _rule_matches(fields, rule):
            continue
        if rule.get("outcome") == "exception":
            return RoutingResult(
                destination=None,
                instruction_required=None,
                reason=rule["label"],
                exception_category=rule["exception_category"],
            )
        return RoutingResult(
            destination=rule["destination"],
            instruction_required=rule["instruction_required"],
            reason=rule["label"],
        )

    category = "unknown_source" if fields.get("source_category") == "unrecognised" else "no_destination"
    return RoutingResult(
        destination=None,
        instruction_required=None,
        reason="No PN routing rule matched",
        exception_category=category,
    )


def route_ocbc(
    fields: dict[str, Any],
    ocbc_source_rules: list[dict[str, Any]],
    ocbc_prefix_overrides: list[dict[str, Any]],
) -> RoutingResult:
    result: RoutingResult | None = None

    for rule in ocbc_source_rules:
        if _rule_matches(fields, rule):
            result = RoutingResult(
                destination=rule["destination"],
                instruction_required=rule["instruction_required"],
                reason=rule["label"],
            )
            break

    for override in ocbc_prefix_overrides:
        if fields.get("account_prefix") == override["account_prefix"]:
            result = RoutingResult(
                destination=override["destination"],
                instruction_required=override["instruction_required"],
                reason=f"Customer prefix {override['account_prefix']} override",
            )
            break

    if result is not None:
        return result

    category = "unknown_source" if fields.get("source_category") == "unrecognised" else "no_destination"
    return RoutingResult(
        destination=None,
        instruction_required=None,
        reason="No OCBC routing rule matched",
        exception_category=category,
    )


def classify_source(source: str | None, electronic_sources: list[str], manual_sources: list[str]) -> str:
    if source in electronic_sources:
        return "electronic"
    if source in manual_sources:
        return "manual"
    return "unrecognised"
