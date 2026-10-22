"""The whole conversion, start to finish: two Esunny exports in, one review workbook out."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.aggregate import aggregate_routed_rows, filter_eligible, route_eligible_rows
from src.exceptions import ExceptionCollector
from src.io import DEFAULT_ENCODINGS, read_closeout, read_filled, write_output
from src.join import enrich_closeout
from src.output import build_ocbc_sheet, build_pn_sheet, build_summary, build_trace, finalize_summary


@dataclass(frozen=True)
class RunResult:
    output_path: Path
    rules_version: str
    closeout_rows: int
    eligible_rows: int
    summary_rows: int
    pn_rows: int
    ocbc_rows: int
    exceptions: int


def run(filled_path: str | Path, closeout_path: str | Path, output_path: str | Path, config: dict) -> RunResult:
    encodings = config.get("input_encodings", DEFAULT_ENCODINGS)

    filled = read_filled(filled_path, encodings=encodings)
    closeout = read_closeout(closeout_path, encodings=encodings)

    exceptions = ExceptionCollector()

    enriched = enrich_closeout(closeout, filled, exceptions)
    eligible = filter_eligible(enriched)
    routed = route_eligible_rows(eligible, config, exceptions)
    aggregated = aggregate_routed_rows(routed)

    summary_full = build_summary(aggregated, config, exceptions)
    pn_sheet = build_pn_sheet(summary_full)
    ocbc_sheet = build_ocbc_sheet(summary_full)
    trace_sheet = build_trace(summary_full, pn_sheet, ocbc_sheet)
    summary_sheet = finalize_summary(summary_full)

    write_output(
        output_path,
        {
            "PN": pn_sheet,
            "OCBC": ocbc_sheet,
            "summary": summary_sheet,
            "exceptions": exceptions.to_dataframe(),
            "trace": trace_sheet,
        },
    )

    return RunResult(
        output_path=Path(output_path),
        rules_version=str(config["rules_version"]),
        closeout_rows=len(closeout),
        eligible_rows=len(eligible),
        summary_rows=len(summary_sheet),
        pn_rows=len(pn_sheet),
        ocbc_rows=len(ocbc_sheet),
        exceptions=len(exceptions),
    )
