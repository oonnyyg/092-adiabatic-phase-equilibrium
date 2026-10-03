"""Build result records and write CSV / JSON reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .solver import solve_experiment

CSV_COLUMNS = (
    "experiment_id", "material_id", "mass_kg",
    "initial_temp_C", "initial_liquid_fraction",
    "final_temp_C", "final_liquid_fraction",
    "initial_enthalpy_J", "final_enthalpy_J", "net_heat_J",
)


def build_results(experiments):
    """Solve every experiment and return (rows, summaries)."""
    rows = []
    summaries = []
    for experiment in experiments:
        temp, fractions = solve_experiment(experiment)
        materials = []
        total_initial = 0.0
        total_final = 0.0
        for material in experiment.materials:
            initial = material.initial_enthalpy()
            final = material.mass * material.specific_enthalpy(
                temp, fractions[material.material_id]
            )
            total_initial += initial
            total_final += final
            record = {
                "experiment_id": experiment.experiment_id,
                "material_id": material.material_id,
                "mass_kg": material.mass,
                "initial_temp_C": material.initial_temp,
                "initial_liquid_fraction": material.initial_liquid_fraction,
                "final_temp_C": temp,
                "final_liquid_fraction": fractions[material.material_id],
                "initial_enthalpy_J": initial,
                "final_enthalpy_J": final,
                "net_heat_J": final - initial,
            }
            rows.append(record)
            materials.append(record)
        summaries.append({
            "experiment_id": experiment.experiment_id,
            "equilibrium_temp_C": temp,
            "total_initial_enthalpy_J": total_initial,
            "total_final_enthalpy_J": total_final,
            "enthalpy_residual_J": total_final - total_initial,
            "materials": materials,
        })
    return rows, summaries


def _format(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return value


def write_reports(rows, summaries, out_dir):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    csv_path = out_path / "materials.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _format(row[key]) for key in CSV_COLUMNS})
    json_path = out_path / "summary.json"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump({"experiments": summaries}, handle, indent=2)
        handle.write("\n")
    return csv_path, json_path
