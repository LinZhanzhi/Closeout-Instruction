"""Loading and checking config.yaml.

The config is bundled inside the executable, so a mistake made while editing it ships to
every user. Every rule is therefore checked when the program starts, and all problems are
reported together in plain language, before a single closeout row is processed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

from src.exceptions import CATEGORIES
from src.routing import OPS, ROUTING_FIELDS

REQUIRED_KEYS = (
    "rules_version",
    "electronic_sources",
    "manual_sources",
    "account_type_map",
    "no_closeout_reason_labels",
    "pn_routing",
    "ocbc_source_rules",
    "ocbc_prefix_overrides",
    "exchange_map",
    "product_map",
    "month_letters",
)

ACCOUNT_TYPES = ("Omnibus", "Speculative")
CLOSEOUT_METHODS = ("manual_instruction", "automatic", "none")
PREFIX_LENGTH = 3  # the customer prefix is the first 3 characters of 资金账号

_LIST_OPS = ("in", "starts_with_any")
_FIXED_VALUES = {
    "contract_type": ("futures", "option"),
    "source_category": ("electronic", "manual", "unrecognised"),
}
_QUOTE_HINT = "must be text - put it in quotes"


class ConfigError(ValueError):
    pass


def bundled_config_path() -> Path:
    # A PyInstaller build unpacks its bundled data files under sys._MEIPASS at runtime.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "config.yaml"


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else bundled_config_path()
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    problems = validate_config(config)
    if problems:
        raise ConfigError(
            f"{path.name} has {len(problems)} problem(s):\n" + "\n".join(f"- {p}" for p in problems)
        )
    return config


def _is_text(value) -> bool:
    return isinstance(value, str) and value != ""


def _check_prefix(where: str, prefix, problems: list[str]) -> None:
    if not _is_text(prefix):
        problems.append(f"{where}: customer prefix {prefix!r} {_QUOTE_HINT}")
    elif len(prefix) != PREFIX_LENGTH:
        problems.append(
            f"{where}: customer prefix {prefix!r} must be exactly {PREFIX_LENGTH} characters "
            "(the first 3 characters of 资金账号)"
        )


def _check_conditions(where: str, rule: dict, problems: list[str]) -> None:
    conditions = rule.get("all_of")
    if not conditions:
        # all() of no conditions is True, so such a rule would swallow every row that reaches it.
        problems.append(f"{where}: needs at least one condition under all_of")
        return

    for cond in conditions:
        field, op, value = cond.get("field"), cond.get("op"), cond.get("value")
        if field not in ROUTING_FIELDS:
            problems.append(f"{where}: unknown field {field!r} (allowed: {', '.join(ROUTING_FIELDS)})")
            continue
        if op not in OPS:
            problems.append(f"{where}: unknown op {op!r} (allowed: {', '.join(OPS)})")
            continue
        if op in _LIST_OPS and not isinstance(value, list):
            problems.append(f"{where}: op '{op}' on {field} needs a list, e.g. [AAA, BBB]")
            continue

        for item in value if op in _LIST_OPS else [value]:
            if field == "account_prefix" and op in ("equals", "in"):
                _check_prefix(where, item, problems)
            elif not _is_text(item):
                problems.append(f"{where}: value {item!r} for {field} {_QUOTE_HINT}")
            elif field in _FIXED_VALUES and item not in _FIXED_VALUES[field]:
                problems.append(
                    f"{where}: {field} cannot be {item!r} (allowed: {', '.join(_FIXED_VALUES[field])})"
                )


def _check_destination(where: str, rule: dict, accounts: dict, problems: list[str]) -> None:
    destination = rule.get("destination")
    if destination not in accounts:
        problems.append(
            f"{where}: destination {destination!r} is not listed in account_type_map - add the "
            "subaccount there first"
        )
        return

    method = accounts[destination].get("closeout_method")
    expected = method == "manual_instruction"
    if rule.get("instruction_required") is not expected:
        problems.append(
            f"{where}: instruction_required must be {str(expected).lower()} because account "
            f"{destination} has closeout_method '{method}'"
        )


def _check_code_map(name: str, code_map: dict, problems: list[str]) -> None:
    for code, targets in code_map.items():
        if not _is_text(code):
            problems.append(f"{name}: code {code!r} {_QUOTE_HINT}")
        if not isinstance(targets, dict) or set(targets) != {"pn", "ocbc"}:
            problems.append(f"{name} {code!r}: needs exactly the two entries pn and ocbc (use null if unknown)")
            continue
        for broker, target in targets.items():
            if target is not None and not _is_text(target):
                problems.append(f"{name} {code!r}: {broker} code {target!r} {_QUOTE_HINT}")


def validate_config(config: dict) -> list[str]:
    missing = [key for key in REQUIRED_KEYS if key not in (config or {})]
    if missing:
        return [f"missing setting(s): {', '.join(missing)}"]

    problems: list[str] = []

    accounts = config["account_type_map"]
    for account, meta in accounts.items():
        if not _is_text(account):
            problems.append(f"account_type_map: account {account!r} {_QUOTE_HINT}")
        if meta.get("account_type") not in ACCOUNT_TYPES:
            problems.append(f"account_type_map {account}: account_type must be one of {', '.join(ACCOUNT_TYPES)}")
        if meta.get("closeout_method") not in CLOSEOUT_METHODS:
            problems.append(
                f"account_type_map {account}: closeout_method must be one of {', '.join(CLOSEOUT_METHODS)}"
            )

    for section in ("pn_routing", "ocbc_source_rules"):
        for rule in config[section]:
            where = f"{section} rule {rule.get('priority')!r} ({rule.get('label')})"
            _check_conditions(where, rule, problems)
            if rule.get("outcome") == "exception":
                if rule.get("exception_category") not in CATEGORIES:
                    problems.append(f"{where}: exception_category must be one of {', '.join(CATEGORIES)}")
            else:
                _check_destination(where, rule, accounts, problems)

    for override in config["ocbc_prefix_overrides"]:
        where = f"ocbc_prefix_overrides {override.get('account_prefix')!r}"
        _check_prefix(where, override.get("account_prefix"), problems)
        _check_destination(where, override, accounts, problems)

    for name in ("electronic_sources", "manual_sources"):
        for source in config[name]:
            if not _is_text(source):
                problems.append(f"{name}: source {source!r} {_QUOTE_HINT}")
    both = set(config["electronic_sources"]) & set(config["manual_sources"])
    if both:
        problems.append(f"sources listed as both electronic and manual: {', '.join(sorted(both))}")

    _check_code_map("exchange_map", config["exchange_map"], problems)
    _check_code_map("product_map", config["product_map"], problems)

    letters = config["month_letters"]
    if len(letters) != 12 or not all(_is_text(letter) for letter in letters):
        problems.append("month_letters: needs exactly 12 letters, January to December")

    return problems
