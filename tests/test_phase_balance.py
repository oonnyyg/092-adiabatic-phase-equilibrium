import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from phase_balance.model import InputError, parse_experiments
from phase_balance.solver import solve_experiment


def make_payload(materials, exp_id="exp1"):
    return {"experiments": [{"id": exp_id, "materials": materials}]}


def base_material(**overrides):
    mat = {
        "id": "a",
        "mass_kg": 1.0,
        "cp_solid": 1000.0,
        "cp_liquid": 2000.0,
        "melting_point_c": 0.0,
        "latent_heat": 100000.0,
        "initial_temp_c": 10.0,
    }
    mat.update(overrides)
    return mat


class SolverTests(unittest.TestCase):
    def solve(self, materials):
        (exp,) = parse_experiments(make_payload(materials))
        return solve_experiment(exp)

    def test_sensible_only_no_phase_change(self):
        res = self.solve(
            [
                base_material(initial_temp_c=40.0),
                base_material(
                    id="b", melting_point_c=-50.0, initial_temp_c=-40.0,
                    cp_solid=500.0, cp_liquid=500.0,
                ),
            ]
        )
        # H = (1e5+2000*40) + (1e5+500*10) = 285000 J; above 0 C the system
        # enthalpy is 225000 + 2500*T, so T = 24 C with no phase change.
        self.assertAlmostEqual(res.final_temp, 24.0, places=7)
        self.assertAlmostEqual(res.residual, 0.0, places=6)

    def test_partial_melting_pins_temperature(self):
        res = self.solve(
            [
                base_material(initial_temp_c=15.0),  # H = 130000 J
                base_material(
                    id="b", melting_point_c=5.0, initial_temp_c=-5.0,
                    cp_solid=1000.0, latent_heat=50000.0,
                ),
            ]
        )
        self.assertAlmostEqual(res.final_temp, 5.0, places=9)
        mat_b = next(m for m in res.materials if m.material_id == "b")
        # H total = 130000 - 10000 = 120000; at 5 C a holds 110000,
        # so b fraction = 10000 / 50000 = 0.2
        self.assertAlmostEqual(mat_b.final_liquid_fraction, 0.2, places=9)
        self.assertAlmostEqual(res.residual, 0.0, places=6)

    def test_initial_fraction_at_melting_point(self):
        res = self.solve(
            [
                base_material(initial_temp_c=0.0, initial_liquid_fraction=0.5),
                base_material(
                    id="b", melting_point_c=100.0, initial_temp_c=100.0,
                    initial_liquid_fraction=1.0, cp_solid=10.0,
                    latent_heat=1000.0,
                ),
            ]
        )
        # H total = 50000 + 1000 = 51000; at 0 C the system holds
        # -1000 (b solid) .. 99000 (a liquid), so T pins at 0 C and
        # a fraction = (51000 + 1000) / 100000 = 0.52
        self.assertAlmostEqual(res.final_temp, 0.0, places=9)
        mat_a = next(m for m in res.materials if m.material_id == "a")
        self.assertAlmostEqual(mat_a.final_liquid_fraction, 0.52, places=9)

    def test_heat_closure_per_material(self):
        res = self.solve(
            [
                base_material(initial_temp_c=50.0),
                base_material(id="b", melting_point_c=30.0, initial_temp_c=-10.0),
                base_material(id="c", melting_point_c=-20.0, initial_temp_c=80.0),
            ]
        )
        net_sum = sum(m.net_heat for m in res.materials)
        self.assertAlmostEqual(net_sum, 0.0, places=6)
        self.assertAlmostEqual(res.residual, 0.0, places=6)


class ValidationTests(unittest.TestCase):
    def test_fraction_required_at_melting_point(self):
        with self.assertRaises(InputError):
            parse_experiments(make_payload([base_material(initial_temp_c=0.0)]))

    def test_fraction_forbidden_away_from_melting_point(self):
        with self.assertRaises(InputError):
            parse_experiments(
                make_payload(
                    [base_material(initial_temp_c=5.0, initial_liquid_fraction=0.2)]
                )
            )

    def test_fraction_out_of_range_rejected(self):
        with self.assertRaises(InputError):
            parse_experiments(
                make_payload(
                    [base_material(initial_temp_c=0.0, initial_liquid_fraction=1.5)]
                )
            )

    def test_duplicate_melting_points_rejected(self):
        with self.assertRaises(InputError):
            parse_experiments(
                make_payload([base_material(), base_material(id="b")])
            )

    def test_non_positive_values_rejected(self):
        with self.assertRaises(InputError):
            parse_experiments(make_payload([base_material(mass_kg=0.0)]))
        with self.assertRaises(InputError):
            parse_experiments(make_payload([base_material(latent_heat=-1.0)]))

    def test_non_finite_rejected(self):
        with self.assertRaises(InputError):
            parse_experiments(
                make_payload([base_material(initial_temp_c=float("nan"))])
            )

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(InputError):
            parse_experiments(
                {
                    "experiments": [
                        {"id": "x", "materials": [base_material()]},
                        {"id": "x", "materials": [base_material()]},
                    ]
                }
            )

    def test_empty_materials_rejected(self):
        with self.assertRaises(InputError):
            parse_experiments({"experiments": [{"id": "x", "materials": []}]})


class CliTests(unittest.TestCase):
    def run_cli(self, payload, out_dir):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(payload, fh)
            path = fh.name
        return subprocess.run(
            [sys.executable, "-m", "phase_balance", path, "--out", str(out_dir)],
            capture_output=True,
            text=True,
        )

    def test_valid_batch_writes_reports(self):
        payload = make_payload(
            [
                base_material(),
                base_material(id="b", melting_point_c=50.0, initial_temp_c=60.0),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = self.run_cli(payload, out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((out / "materials.csv").exists())
            summary = json.loads((out / "summary.json").read_text("utf-8"))
            exp = summary["experiments"][0]
            self.assertAlmostEqual(exp["enthalpy_residual_j"], 0.0, places=6)

    def test_invalid_batch_fails_without_reports(self):
        payload = make_payload([base_material(mass_kg=-3.0)])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = self.run_cli(payload, out)
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse((out / "materials.csv").exists())
            self.assertFalse((out / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
