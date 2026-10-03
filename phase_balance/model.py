"""Data model, validation and enthalpy functions.

Units: mass kg, energy J, temperature degC.
Enthalpy reference: fully solid at the material's melting point is zero.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


class InputError(ValueError):
    """Raised when the experiment input is invalid."""


def _finite_number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{what} must be a number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise InputError(f"{what} must be finite, got {value!r}")
    return value


def _positive(value, what):
    value = _finite_number(value, what)
    if value <= 0.0:
        raise InputError(f"{what} must be positive, got {value!r}")
    return value


@dataclass(frozen=True)
class Material:
    material_id: str
    mass: float
    cp_solid: float
    cp_liquid: float
    melting_point: float
    latent_heat: float
    initial_temp: float
    initial_liquid_fraction: float | None

    def specific_enthalpy(self, temp, fraction=None):
        """Specific enthalpy (J/kg) relative to solid at the melting point."""
        tm = self.melting_point
        if temp < tm:
            return self.cp_solid * (temp - tm)
        if temp > tm:
            return self.latent_heat + self.cp_liquid * (temp - tm)
        frac = 1.0 if fraction is None else fraction
        return self.latent_heat * frac

    def enthalpy(self, temp, fraction=None):
        return self.mass * self.specific_enthalpy(temp, fraction)

    def initial_enthalpy(self):
        return self.enthalpy(self.initial_temp, self.initial_liquid_fraction)


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    materials: tuple


def _parse_material(raw, exp_id, index):
    where = f"experiment {exp_id!r} material[{index}]"
    if not isinstance(raw, dict):
        raise InputError(f"{where} must be an object")
    mid = raw.get("id")
    if not isinstance(mid, str) or not mid:
        raise InputError(f"{where}: 'id' must be a non-empty string")
    prefix = f"{where} ({mid!r})"
    mass = _positive(raw.get("mass_kg"), f"{prefix} mass_kg")
    cp_s = _positive(raw.get("cp_solid"), f"{prefix} cp_solid")
    cp_l = _positive(raw.get("cp_liquid"), f"{prefix} cp_liquid")
    tm = _finite_number(raw.get("melting_point_c"), f"{prefix} melting_point_c")
    latent = _positive(raw.get("latent_heat"), f"{prefix} latent_heat")
    t0 = _finite_number(raw.get("initial_temp_c"), f"{prefix} initial_temp_c")

    frac = raw.get("initial_liquid_fraction")
    if t0 != tm:
        if frac is not None:
            raise InputError(
                f"{prefix}: initial_liquid_fraction only allowed when "
                "initial_temp_c equals melting_point_c"
            )
        frac = None
    else:
        if frac is None:
            raise InputError(
                f"{prefix}: initial_liquid_fraction required when "
                "initial_temp_c equals melting_point_c"
            )
        frac = _finite_number(frac, f"{prefix} initial_liquid_fraction")
        if not 0.0 <= frac <= 1.0:
            raise InputError(
                f"{prefix}: initial_liquid_fraction must be in [0, 1], got {frac!r}"
            )
    return Material(mid, mass, cp_s, cp_l, tm, latent, t0, frac)


def parse_experiments(data):
    if not isinstance(data, dict) or not isinstance(data.get("experiments"), list):
        raise InputError("top level must be an object with an 'experiments' array")
    experiments = []
    seen_exp = set()
    for i, raw in enumerate(data["experiments"]):
        if not isinstance(raw, dict):
            raise InputError(f"experiment[{i}] must be an object")
        exp_id = raw.get("id")
        if not isinstance(exp_id, str) or not exp_id:
            raise InputError(f"experiment[{i}]: 'id' must be a non-empty string")
        if exp_id in seen_exp:
            raise InputError(f"duplicate experiment id {exp_id!r}")
        seen_exp.add(exp_id)
        raw_materials = raw.get("materials")
        if not isinstance(raw_materials, list) or not raw_materials:
            raise InputError(f"experiment {exp_id!r} needs at least one material")
        materials = tuple(
            _parse_material(m, exp_id, j) for j, m in enumerate(raw_materials)
        )
        ids = [m.material_id for m in materials]
        if len(set(ids)) != len(ids):
            raise InputError(f"experiment {exp_id!r}: duplicate material id")
        mps = [m.melting_point for m in materials]
        if len(set(mps)) != len(mps):
            raise InputError(f"experiment {exp_id!r}: melting points must differ")
        experiments.append(Experiment(exp_id, materials))
    return experiments
