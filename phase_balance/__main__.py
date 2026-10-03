"""CLI: python -m phase_balance input.json --out output_dir"""
from __future__ import annotations

import argparse
import json
import sys

from .model import InputError, parse_experiments
from .report import write_reports
from .solver import solve_experiment


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="phase_balance",
        description="Adiabatic phase-equilibrium calculator (kg, J, degC).",
    )
    parser.add_argument("input", help="input JSON file with experiments")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args(argv)

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read input: {exc}", file=sys.stderr)
        return 2

    try:
        experiments = parse_experiments(data)
    except InputError as exc:
        print(f"error: invalid input: {exc}", file=sys.stderr)
        return 2

    results = [solve_experiment(exp) for exp in experiments]
    csv_path, json_path = write_reports(results, args.out)
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
