"""The config is edited by IT and bundled into the executable, so the startup check is the
only thing standing between a typo and every user's output. These tests make the mistakes
IT is most likely to make and confirm each one is caught with a usable message."""
import copy

import pytest
import yaml

from src.config import ConfigError, load_config, validate_config
from src.routing import route_ocbc, route_pn


@pytest.fixture
def cfg(config) -> dict:
    return copy.deepcopy(config)


def pn_client_rule(prefix, destination, instruction_required):
    return {
        "priority": "new",
        "label": f"Customer prefix {prefix}",
        "all_of": [{"field": "account_prefix", "op": "equals", "value": prefix}],
        "destination": destination,
        "instruction_required": instruction_required,
    }


def fields(**overrides):
    base = {
        "account_prefix": "XYZ",
        "exchange": "SGX",
        "contract_product": "UC",
        "contract_type": "futures",
        "source_category": "electronic",
        "internal_account": "XYZ1DEFG",
    }
    base.update(overrides)
    return base


def test_shipped_config_is_valid(config):
    assert validate_config(config) == []


# --- the maintenance cases IT will actually do ---


def test_new_pn_client_on_a_new_pn_subaccount(cfg):
    cfg["account_type_map"]["BNS8099"] = {"account_type": "Speculative", "closeout_method": "none"}
    cfg["pn_routing"].insert(0, pn_client_rule("NEW", "BNS8099", False))

    assert validate_config(cfg) == []
    result = route_pn(fields(account_prefix="NEW"), cfg["pn_routing"])
    assert (result.destination, result.instruction_required) == ("BNS8099", False)
    # everyone else is routed exactly as before
    assert route_pn(fields(), cfg["pn_routing"]).destination == "BNS8001"


def test_new_ocbc_client_on_a_new_ocbc_subaccount(cfg):
    cfg["account_type_map"]["A2123N-B11"] = {"account_type": "Speculative", "closeout_method": "none"}
    cfg["ocbc_prefix_overrides"].append(
        {"account_prefix": "NEW", "destination": "A2123N-B11", "instruction_required": False}
    )

    assert validate_config(cfg) == []
    result = route_ocbc(fields(account_prefix="NEW"), cfg["ocbc_source_rules"], cfg["ocbc_prefix_overrides"])
    assert (result.destination, result.instruction_required) == ("A2123N-B11", False)
    untouched = route_ocbc(fields(), cfg["ocbc_source_rules"], cfg["ocbc_prefix_overrides"])
    assert untouched.destination == "A2123N-B3"


# --- the mistakes IT might make while doing them ---


def problems_text(cfg) -> str:
    return "\n".join(validate_config(cfg))


def test_rule_pointing_at_a_subaccount_that_was_never_added(cfg):
    cfg["pn_routing"].insert(0, pn_client_rule("NEW", "BNS8099", False))
    assert "'BNS8099' is not listed in account_type_map" in problems_text(cfg)


def test_instruction_required_contradicting_the_subaccount(cfg):
    # BNS8888 is a "no need close-out" account; asking for an instruction would send one out.
    cfg["pn_routing"].insert(0, pn_client_rule("NEW", "BNS8888", True))
    assert "instruction_required must be false because account BNS8888" in problems_text(cfg)


def test_prefix_that_is_not_three_characters(cfg):
    cfg["pn_routing"].insert(0, pn_client_rule("NEWC", "BNS8888", False))
    assert "customer prefix 'NEWC' must be exactly 3 characters" in problems_text(cfg)


def test_all_digit_prefix_written_without_quotes(cfg):
    # YAML reads an unquoted 123 as a number, which would never equal the text prefix "123".
    cfg["ocbc_prefix_overrides"].append(
        {"account_prefix": 123, "destination": "A2123N-B10", "instruction_required": False}
    )
    assert "customer prefix 123 must be text - put it in quotes" in problems_text(cfg)


def test_misspelled_field_op_and_value(cfg):
    rule = pn_client_rule("NEW", "BNS8888", False)
    rule["all_of"] = [
        {"field": "acount_prefix", "op": "equals", "value": "NEW"},
        {"field": "exchange", "op": "equal", "value": "SGX"},
        {"field": "contract_type", "op": "equals", "value": "options"},
    ]
    cfg["pn_routing"].insert(0, rule)
    text = problems_text(cfg)
    assert "unknown field 'acount_prefix'" in text
    assert "unknown op 'equal'" in text
    assert "contract_type cannot be 'options'" in text


def test_rule_with_no_conditions_would_swallow_everything(cfg):
    rule = pn_client_rule("NEW", "BNS8888", False)
    rule["all_of"] = []
    cfg["pn_routing"].insert(0, rule)
    assert "needs at least one condition" in problems_text(cfg)


def test_unknown_account_type_and_closeout_method(cfg):
    cfg["account_type_map"]["BNS8099"] = {"account_type": "Omnibuss", "closeout_method": "manual"}
    text = problems_text(cfg)
    assert "account_type_map BNS8099: account_type must be one of" in text
    assert "account_type_map BNS8099: closeout_method must be one of" in text


def test_product_code_missing_a_broker_entry(cfg):
    cfg["product_map"]["MEG"] = {"ocbc": "MEG"}
    assert "product_map 'MEG': needs exactly the two entries pn and ocbc" in problems_text(cfg)


def test_load_config_reports_every_problem_at_once(cfg, tmp_path):
    cfg["pn_routing"].insert(0, pn_client_rule("NEWC", "BNS8099", False))
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ConfigError) as error:
        load_config(path)

    message = str(error.value)
    assert "config.yaml has 2 problem(s)" in message
    assert "NEWC" in message and "BNS8099" in message
