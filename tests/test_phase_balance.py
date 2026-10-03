import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from phase_balance.report import build_results
from phase_balance.solver import (
    Experiment,
    Material,
    ValidationError,
    parse_experiments,
    solve_experiment,
)


def make_material(**overrides):
    data = {
        "id": "m",
        "mass": 1.0,
        "cp_solid": 2.0,
        "cp_liquid": 4.0,
        "melt_point": 0.0,
        "latent_heat": 100.0,
        "initial_temp": 10.0,
    }
    data.update(overrides)
    return Material.from_dict(data, "test")


class SolverTests(unittest.TestCase):
    def test_plain_heat_exchange_between_segments(self):
        hot = make_material(initial_temp=10.0)  # H = 100 + 4*10 = 140
        cold = make_material(
            id="cold", cp_solid=1.0, cp_liquid=3.0,
            melt_point=10.0, latent_heat=50.0, initial_temp=0.0,
        )  # H = 1*(0-10) = -10
        exp = Experiment("e1", (hot, cold))
        temp, fractions = solve_experiment(exp)
        self.assertAlmostEqual(temp, 8.0, places=7)
        self.assertEqual(fractions["m"], 1.0)
        self.assertEqual(fractions["cold"], 0.0)

    def test_temperature_parks_at_melt_point_for_partial_melt(self):
        hot = make_material(initial_temp=12.0)  # H = 148
        cold = make_material(
            id="cold", cp_solid=1.0, cp_liquid=3.0, melt_point=10.0,
            latent_heat=500.0, initial_temp=10.0, initial_liquid_fraction=0.0,
        )
        exp = Experiment("e1", (hot, cold))
        temp, fractions = solve_experiment(exp)
        self.assertAlmostEqual(temp, 10.0, places=7)
        self.assertAlmostEqual(fractions["cold"], 8.0 / 500.0, places=8)
        self.assertEqual(fractions["m"], 1.0)

    def test_full_melt_above_all_melt_points(self):
        hot = make_material(initial_temp=1000.0)
        cold = make_material(
            id="cold", melt_point=5.0, latent_heat=10.0, initial_temp=-5.0,
        )
        exp = Experiment("e1", (hot, cold))
        temp, fractions = solve_experiment(exp)
        self.assertGreater(temp, 5.0)
        self.assertEqual(fractions, {"m": 1.0, "cold": 1.0})

    def test_enthalpy_residual_is_closed(self):
        hot = make_material(initial_temp=37.5)
        cold = make_material(
            id="cold", mass=2.5, cp_solid=1.5, cp_liquid=2.5,
            melt_point=-20.0, latent_heat=80.0, initial_temp=-20.0,
            initial_liquid_fraction=0.3,
        )
        exp = Experiment("e1", (hot, cold))
        _, summaries = build_results([exp])
        summary = summaries[0]
        self.assertAlmostEqual(
            summary["enthalpy_residual_J"], 0.0, places=6
        )
        net = sum(m["net_heat_J"] for m in summary["materials"])
        self.assertAlmostEqual(net, 0.0, places=6)


class ValidationTests(unittest.TestCase):
    def _parse(self, experiments):
        return parse_experiments({"experiments": experiments})

    def _experiment(self, materials, exp_id="e1"):
        return {"id": exp_id, "materials": materials}

    def _material(self, **overrides):
        data = {
            "id": "m", "mass": 1.0, "cp_solid": 2.0, "cp_liquid": 4.0,
            "melt_point": 0.0, "latent_heat": 100.0, "initial_temp": 5.0,
        }
        data.update(overrides)
        return data

    def test_fraction_required_exactly_at_melt_point(self):
        material = self._material(initial_temp=0.0)
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([material])])

    def test_fraction_forbidden_away_from_melt_point(self):
        material = self._material(initial_liquid_fraction=0.5)
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([material])])

    def test_fraction_bounds(self):
        material = self._material(initial_temp=0.0, initial_liquid_fraction=1.5)
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([material])])

    def test_duplicate_melt_points_rejected(self):
        first = self._material(id="a")
        second = self._material(id="b")
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([first, second])])

    def test_duplicate_material_ids_rejected(self):
        first = self._material(melt_point=0.0)
        second = self._material(melt_point=10.0)
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([first, second])])

    def test_duplicate_experiment_ids_rejected(self):
        material = self._material()
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([material], "x"),
                         self._experiment([material], "x")])

    def test_non_positive_values_rejected(self):
        for key in ("mass", "cp_solid", "cp_liquid", "latent_heat"):
            material = self._material(**{key: 0.0})
            with self.assertRaises(ValidationError, msg=key):
                self._parse([self._experiment([material])])

    def test_non_finite_values_rejected(self):
        material = self._material(initial_temp=float("nan"))
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([material])])

    def test_empty_materials_rejected(self):
        with self.assertRaises(ValidationError):
            self._parse([self._experiment([])])


class CliTests(unittest.TestCase):
    def _run_cli(self, payload, tmpdir):
        input_path = Path(tmpdir) / "input.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")
        out_dir = Path(tmpdir) / "out"
        proc = subprocess.run(
            [sys.executable, "-m", "phase_balance", str(input_path),
             "--out", str(out_dir)],
            capture_output=True, text=True,
        )
        return proc, out_dir

    def _valid_payload(self):
        return {"experiments": [{
            "id": "mix",
            "materials": [
                {"id": "hot", "mass": 1.0, "cp_solid": 2.0,
                 "cp_liquid": 4.0, "melt_point": 0.0,
                 "latent_heat": 100.0, "initial_temp": 12.0},
                {"id": "cold", "mass": 1.0, "cp_solid": 1.0,
                 "cp_liquid": 3.0, "melt_point": 10.0,
                 "latent_heat": 500.0, "initial_temp": 10.0,
                 "initial_liquid_fraction": 0.0},
            ],
        }]}

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            proc, out_dir = self._run_cli(self._valid_payload(), tmpdir)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            csv_path = out_dir / "materials.csv"
            json_path = out_dir / "summary.json"
            self.assertTrue(csv_path.is_file())
            self.assertTrue(json_path.is_file())
            with csv_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            summary = json.loads(json_path.read_text(encoding="utf-8"))
            entry = summary["experiments"][0]
            self.assertAlmostEqual(
                entry["equilibrium_temp_C"], 10.0, delta=1e-7
            )
            self.assertAlmostEqual(
                entry["enthalpy_residual_J"], 0.0, delta=1e-6
            )
            cold = next(
                m for m in entry["materials"] if m["material_id"] == "cold"
            )
            self.assertAlmostEqual(
                cold["final_liquid_fraction"], 0.016, delta=1e-8
            )

    def test_invalid_batch_fails_without_reports(self):
        payload = self._valid_payload()
        payload["experiments"].append({
            "id": "bad",
            "materials": [
                {"id": "x", "mass": -1.0, "cp_solid": 2.0,
                 "cp_liquid": 4.0, "melt_point": 0.0,
                 "latent_heat": 100.0, "initial_temp": 5.0},
            ],
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            proc, out_dir = self._run_cli(payload, tmpdir)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("error", proc.stderr.lower())
            self.assertFalse((out_dir / "materials.csv").exists())
            self.assertFalse((out_dir / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
