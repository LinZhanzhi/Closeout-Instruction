from pathlib import Path

import pandas as pd
import pytest

from src.io import read_closeout, read_filled

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FILLED_SAMPLE = PROJECT_ROOT / "input" / "filled_sample.csv"
CLOSEOUT_SAMPLE = PROJECT_ROOT / "input" / "close out_sample.csv"


def reencode(src: Path, dst: Path, encoding: str) -> Path:
    dst.write_bytes(src.read_bytes().decode("gbk").encode(encoding))
    return dst


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-8"])
def test_filled_reads_identically_from_gbk_and_utf8(tmp_path, encoding):
    # Operations hit a UnicodeDecodeError when a day's filled export arrived as UTF-8 instead
    # of GBK. Both must now read to exactly the same data with no config change.
    from_gbk = read_filled(FILLED_SAMPLE)
    from_utf8 = read_filled(reencode(FILLED_SAMPLE, tmp_path / "filled.csv", encoding))
    pd.testing.assert_frame_equal(from_gbk, from_utf8)


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-8"])
def test_closeout_reads_identically_from_gbk_and_utf8(tmp_path, encoding):
    from_gbk = read_closeout(CLOSEOUT_SAMPLE)
    from_utf8 = read_closeout(reencode(CLOSEOUT_SAMPLE, tmp_path / "closeout.csv", encoding))
    pd.testing.assert_frame_equal(from_gbk, from_utf8)


def test_unreadable_file_raises_clear_error(tmp_path):
    bad = reencode(FILLED_SAMPLE, tmp_path / "filled.csv", "utf-16")
    with pytest.raises(ValueError, match="Could not read filled export"):
        read_filled(bad)


def test_missing_column_raises_clear_error(tmp_path):
    no_t1 = tmp_path / "filled.csv"
    no_t1.write_text("成交号,成交来源\nEX1,程式单\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="missing columns"):
        read_filled(no_t1)
