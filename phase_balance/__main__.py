"""Command line entry: python -m phase_balance input.json --out DIR."""

from __future__ import annotations

import argparse
import json
import sys

from .report import build_results, write_reports
from .solver import ValidationError, parse_experiments


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="phase_balance",
        description=(
            "Adiabatic mixing: common equilibrium temperature and liquid "
            "fractions for materials that only exchange heat."
        ),
    )
    parser.add_argument("input", help="path to the input JSON file")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)

    try:
        with open(args.input, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2
    try:
        experiments = parse_experiments(payload)
    except ValidationError as exc:
        print(f"error: invalid experiment data: {exc}", file=sys.stderr)
        return 2

    rows, summaries = build_results(experiments)
    csv_path, json_path = write_reports(rows, summaries, args.out)
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
