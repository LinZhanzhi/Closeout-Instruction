"""End-to-end regression test against the real sample CSVs, through the same run() the
window and the command line both use.

These numbers were established by independently reconstructing the join/eligibility/
aggregation in a throwaway script during development - they act as a regression guard, not
a spec. If a deliberate logic change moves them, update the expected values and say why.
"""
from pathlib import Path

import pandas as pd

from src.pipeline import run

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FILLED_PATH = PROJECT_ROOT / "input" / "filled_sample.csv"
CLOSEOUT_PATH = PROJECT_ROOT / "input" / "close out_sample.csv"


def test_sample_files_produce_expected_workbook(config, tmp_path):
    output_path = tmp_path / "out.xlsx"

    result = run(FILLED_PATH, CLOSEOUT_PATH, output_path, config)

    assert result.rules_version == config["rules_version"]
    assert result.closeout_rows == 581
    assert result.eligible_rows == 289
    assert result.summary_rows == 18
    assert result.pn_rows == 13
    assert result.ocbc_rows == 5
    assert result.exceptions == 0

    sheets = pd.read_excel(output_path, sheet_name=None)
    assert list(sheets) == ["PN", "OCBC", "summary", "exceptions", "trace"]
    assert len(sheets["PN"]) == 13
    assert len(sheets["OCBC"]) == 5
    assert len(sheets["trace"]) == 18
    assert sheets["summary"]["Traded_Qty"].sum() == 500


def test_completely_empty_account_cell_is_reported_not_a_crash(config, tmp_path):
    filled = tmp_path / "filled.csv"
    closeout = tmp_path / "closeout.csv"
    filled.write_text("成交号,T+1,成交来源\nEX1,否,程式单\n", encoding="utf-8-sig")
    closeout.write_text(
        "资金账号,市场,合约,数量,合约类型,平仓成交号,平仓会员号\n,SGX,UC 2609,1,期货,EX1,400\n",
        encoding="utf-8-sig",
    )
    output_path = tmp_path / "out.xlsx"

    result = run(filled, closeout, output_path, config)

    assert (result.eligible_rows, result.pn_rows, result.exceptions) == (1, 0, 1)
    assert list(pd.read_excel(output_path, sheet_name="exceptions")["category"]) == ["blank_account"]
