"""CSV / JSON report writers."""
from __future__ import annotations

import csv
import json
from pathlib import Path

CSV_FIELDS = [
    "experiment_id",
    "material_id",
    "final_temp_c",
    "final_liquid_fraction",
    "initial_enthalpy_j",
    "final_enthalpy_j",
    "net_heat_j",
]


def write_reports(results, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / "materials.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for res in results:
            for mat in res.materials:
                writer.writerow(
                    {
                        "experiment_id": res.experiment_id,
                        "material_id": mat.material_id,
                        "final_temp_c": f"{mat.final_temp:.12g}",
                        "final_liquid_fraction": f"{mat.final_liquid_fraction:.12g}",
                        "initial_enthalpy_j": f"{mat.initial_enthalpy:.12g}",
                        "final_enthalpy_j": f"{mat.final_enthalpy:.12g}",
                        "net_heat_j": f"{mat.net_heat:.12g}",
                    }
                )

    summary = {
        "experiments": [
            {
                "id": res.experiment_id,
                "final_temp_c": res.final_temp,
                "initial_enthalpy_j": res.initial_enthalpy,
                "final_enthalpy_j": res.final_enthalpy,
                "enthalpy_residual_j": res.residual,
                "materials": [
                    {
                        "id": mat.material_id,
                        "final_temp_c": mat.final_temp,
                        "final_liquid_fraction": mat.final_liquid_fraction,
                        "initial_enthalpy_j": mat.initial_enthalpy,
                        "final_enthalpy_j": mat.final_enthalpy,
                        "net_heat_j": mat.net_heat,
                    }
                    for mat in res.materials
                ],
            }
            for res in results
        ]
    }
    json_path = out / "summary.json"
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return csv_path, json_path
