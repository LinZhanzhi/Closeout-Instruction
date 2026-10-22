import pytest

from src.routing import classify_source, route_ocbc, route_pn


def pn_fields(**overrides):
    fields = {
        "account_prefix": "XYZ",
        "exchange": "CME",
        "contract_product": "CN",
        "contract_type": "futures",
        "source_category": "electronic",
        "internal_account": "XYZ1DEFG",
    }
    fields.update(overrides)
    return fields


def ocbc_fields(**overrides):
    fields = {
        "account_prefix": "XYZ",
        "exchange": "SGX",
        "contract_product": "UC",
        "contract_type": "futures",
        "source_category": "electronic",
        "internal_account": "XYZ1DEFG",
    }
    fields.update(overrides)
    return fields


# --- PN priorities 1-14 (config.yaml pn_routing) ---


def test_pn_priority1_duk_prefix(config):
    r = route_pn(pn_fields(account_prefix="DUK"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8888", False)


def test_pn_priority2_eli_prefix(config):
    r = route_pn(pn_fields(account_prefix="ELI"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8889", False)


def test_pn_priority3_glo_prefix(config):
    r = route_pn(pn_fields(account_prefix="GLO"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8005/6", False)


def test_pn_priority4_cpo_contract(config):
    r = route_pn(pn_fields(contract_product="CPO"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8004", False)


def test_pn_priority5_gle_prefix_uc_or_fe(config):
    r_uc = route_pn(pn_fields(account_prefix="GLE", contract_product="UC"), config["pn_routing"])
    r_fe = route_pn(pn_fields(account_prefix="GLE", contract_product="FEF"), config["pn_routing"])
    assert (r_uc.destination, r_uc.instruction_required) == ("BNS8007", False)
    assert (r_fe.destination, r_fe.instruction_required) == ("BNS8007", False)


def test_pn_priority5b_gle_other_product_has_no_destination(config):
    # Legacy quirk (handover doc, PN table row "5a"): GLE customers trading anything other
    # than UC/FE get no destination at all - this branch never falls through to HKEX/KRX/
    # source-based rules.
    r = route_pn(pn_fields(account_prefix="GLE", contract_product="PX"), config["pn_routing"])
    assert r.is_exception
    assert r.exception_category == "no_destination"


def test_pn_wonderland_uc_goes_to_bns8010_without_instruction(config):
    r = route_pn(pn_fields(account_prefix="WON", exchange="SGX", contract_product="UC"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8010", False)


def test_pn_wonderland_other_products_unchanged(config):
    r = route_pn(pn_fields(account_prefix="WON", exchange="SGX", contract_product="TF"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8001", True)


def test_pn_priority6_hkex_sul(config):
    r = route_pn(pn_fields(exchange="HKEX", account_prefix="SUL"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8888", False)


def test_pn_priority7_hkex_oly_or_kin(config):
    r_oly = route_pn(pn_fields(exchange="HKEX", account_prefix="OLY"), config["pn_routing"])
    r_kin = route_pn(pn_fields(exchange="HKEX", account_prefix="KIN"), config["pn_routing"])
    assert (r_oly.destination, r_oly.instruction_required) == ("BNS8008", False)
    assert (r_kin.destination, r_kin.instruction_required) == ("BNS8008", False)


def test_pn_priority8_other_hkex(config):
    r = route_pn(pn_fields(exchange="HKEX", account_prefix="ZZZ"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8001", True)


def test_pn_priority9_krx(config):
    r = route_pn(pn_fields(exchange="KRX"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8003", True)


def test_pn_priority10_electronic_option_ose_nk225_or_jpn(config):
    r_nk = route_pn(
        pn_fields(exchange="OSE", contract_type="option", contract_product="NK225", source_category="electronic"),
        config["pn_routing"],
    )
    r_jpn = route_pn(
        pn_fields(exchange="OSE", contract_type="option", contract_product="JPN", source_category="electronic"),
        config["pn_routing"],
    )
    assert (r_nk.destination, r_nk.instruction_required) == ("BNS8001", True)
    assert (r_jpn.destination, r_jpn.instruction_required) == ("BNS8001", True)


def test_pn_priority11_other_electronic_option(config):
    r = route_pn(
        pn_fields(exchange="CME", contract_type="option", contract_product="CUS", source_category="electronic"),
        config["pn_routing"],
    )
    assert (r.destination, r.instruction_required) == ("BNS8000", True)


def test_pn_priority12_electronic_futures(config):
    r = route_pn(pn_fields(source_category="electronic"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8001", True)


def test_pn_priority13_manual_source(config):
    r = route_pn(pn_fields(source_category="manual"), config["pn_routing"])
    assert (r.destination, r.instruction_required) == ("BNS8002", True)


def test_pn_priority14_unrecognised_source(config):
    r = route_pn(pn_fields(source_category="unrecognised"), config["pn_routing"])
    assert r.is_exception
    assert r.exception_category == "unknown_source"


def test_pn_earlier_priority_wins_over_later(config):
    # DUK prefix must win even though the contract also begins CPO and the exchange is HKEX.
    r = route_pn(
        pn_fields(account_prefix="DUK", contract_product="CPO", exchange="HKEX"),
        config["pn_routing"],
    )
    assert r.destination == "BNS8888"


# --- OCBC source rules + prefix overrides (config.yaml ocbc_source_rules / ocbc_prefix_overrides) ---


@pytest.mark.parametrize("internal_account", ["232P", "239P"])
def test_ocbc_electronic_exact_account_no_email(config, internal_account):
    r = route_ocbc(
        ocbc_fields(source_category="electronic", internal_account=internal_account),
        config["ocbc_source_rules"],
        config["ocbc_prefix_overrides"],
    )
    assert (r.destination, r.instruction_required) == ("A2123N-B2", False)


def test_ocbc_other_electronic(config):
    r = route_ocbc(ocbc_fields(source_category="electronic"), config["ocbc_source_rules"], config["ocbc_prefix_overrides"])
    assert (r.destination, r.instruction_required) == ("A2123N-B3", True)


@pytest.mark.parametrize("prefix", ["TOR", "SPA"])
def test_ocbc_manual_tor_or_spa(config, prefix):
    r = route_ocbc(
        ocbc_fields(source_category="manual", account_prefix=prefix),
        config["ocbc_source_rules"],
        config["ocbc_prefix_overrides"],
    )
    assert (r.destination, r.instruction_required) == ("A2123N-B5", False)


def test_ocbc_other_manual(config):
    r = route_ocbc(ocbc_fields(source_category="manual"), config["ocbc_source_rules"], config["ocbc_prefix_overrides"])
    assert (r.destination, r.instruction_required) == ("A2123N-B1", True)


@pytest.mark.parametrize(
    "prefix,expected",
    [("DUK", "A2123N-B10"), ("ETE", "A2123N-B7"), ("LAK", "A2123N-B8"), ("SUL", "A2123N-B9")],
)
def test_ocbc_prefix_overrides_apply_regardless_of_source(config, prefix, expected):
    # Overrides apply even when the source rule would otherwise have routed to A2123N-B3.
    r = route_ocbc(
        ocbc_fields(source_category="electronic", account_prefix=prefix),
        config["ocbc_source_rules"],
        config["ocbc_prefix_overrides"],
    )
    assert (r.destination, r.instruction_required) == (expected, False)


def test_ocbc_unrecognised_source_with_no_override_is_exception(config):
    r = route_ocbc(
        ocbc_fields(source_category="unrecognised"),
        config["ocbc_source_rules"],
        config["ocbc_prefix_overrides"],
    )
    assert r.is_exception
    assert r.exception_category == "unknown_source"


def test_ocbc_prefix_override_rescues_unrecognised_source(config):
    # "regardless of source" - even an unrecognised-source row is rescued by a prefix match.
    r = route_ocbc(
        ocbc_fields(source_category="unrecognised", account_prefix="DUK"),
        config["ocbc_source_rules"],
        config["ocbc_prefix_overrides"],
    )
    assert (r.destination, r.instruction_required) == ("A2123N-B10", False)


# --- source classification ---


def test_classify_source(config):
    electronic = config["electronic_sources"]
    manual = config["manual_sources"]
    assert classify_source("程式单", electronic, manual) == "electronic"
    assert classify_source("人工单", electronic, manual) == "manual"
    assert classify_source("Bloomberg", electronic, manual) == "unrecognised"
    assert classify_source(None, electronic, manual) == "unrecognised"
