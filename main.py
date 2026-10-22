"""Convert Esunny filled/closeP exports into Phillip Nova + OCBC closeout instructions.

Run with no arguments (or double-click the built program) to choose the two files in a window.

Scripted use, no window:
    python main.py --filled FILLED.csv --closeout CLOSEOUT.csv [--output OUT.xlsx] [--config config.yaml]
"""
from __future__ import annotations

import argparse
import sys

from src.config import ConfigError, load_config
from src.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--filled")
    parser.add_argument("--closeout")
    parser.add_argument("--output", default="output/closeout_output.xlsx")
    parser.add_argument("--config", help="use this config.yaml instead of the bundled one, e.g. to try out a rule change")
    args = parser.parse_args()

    if not args.filled and not args.closeout:
        from src.gui import launch  # imported here so scripted runs work on machines without Tk

        launch(args.config)
        return
    if not (args.filled and args.closeout):
        parser.error("give both --filled and --closeout, or neither to open the window")

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        sys.exit(str(exc))
    result = run(args.filled, args.closeout, args.output, config)

    print(f"rules version:           {result.rules_version}")
    print(f"closeP rows read:        {result.closeout_rows}")
    print(f"eligible (member+T+1):   {result.eligible_rows}")
    print(f"summary rows:            {result.summary_rows}")
    print(f"PN instruction rows:     {result.pn_rows}")
    print(f"OCBC instruction rows:   {result.ocbc_rows}")
    print(f"exceptions:              {result.exceptions}")
    print(f"wrote {result.output_path}")


if __name__ == "__main__":
    main()
