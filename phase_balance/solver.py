"""Validation, enthalpy model and equilibrium solver."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class ValidationError(ValueError):
    """Raised when an experiment definition is invalid."""


def _finite_number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{what} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise ValidationError(f"{what} must be finite, got {value!r}")
    return float(value)


def _positive(value, what):
    number = _finite_number(value, what)
    if number <= 0.0:
        raise ValidationError(f"{what} must be positive, got {value!r}")
    return number


@dataclass(frozen=True)
class Material:
    """One material. Enthalpy zero point: fully solid at its melt point."""

    material_id: str
    mass: float
    cp_solid: float
    cp_liquid: float
    melt_point: float
    latent_heat: float
    initial_temp: float
    initial_liquid_fraction: float | None = None

    @classmethod
    def from_dict(cls, data, context):
        if not isinstance(data, dict):
            raise ValidationError(f"{context}: material must be an object")
        required = (
            "id", "mass", "cp_solid", "cp_liquid",
            "melt_point", "latent_heat", "initial_temp",
        )
        for key in required:
            if key not in data:
                raise ValidationError(f"{context}: missing field {key!r}")
        material_id = data["id"]
        if not isinstance(material_id, str) or not material_id:
            raise ValidationError(f"{context}: 'id' must be a non-empty string")
        where = f"{context} material {material_id!r}"
        material = cls(
            material_id=material_id,
            mass=_positive(data["mass"], f"{where}: mass"),
            cp_solid=_positive(data["cp_solid"], f"{where}: cp_solid"),
            cp_liquid=_positive(data["cp_liquid"], f"{where}: cp_liquid"),
            melt_point=_finite_number(data["melt_point"], f"{where}: melt_point"),
            latent_heat=_positive(data["latent_heat"], f"{where}: latent_heat"),
            initial_temp=_finite_number(
                data["initial_temp"], f"{where}: initial_temp"
            ),
        )
        fraction = data.get("initial_liquid_fraction")
        at_melt_point = material.initial_temp == material.melt_point
        if at_melt_point:
            if fraction is None:
                raise ValidationError(
                    f"{where}: initial_temp equals melt_point, "
                    "'initial_liquid_fraction' in [0, 1] is required"
                )
            fraction = _finite_number(
                fraction, f"{where}: initial_liquid_fraction"
            )
            if not 0.0 <= fraction <= 1.0:
                raise ValidationError(
                    f"{where}: initial_liquid_fraction must be in [0, 1], "
                    f"got {fraction!r}"
                )
            object.__setattr__(material, "initial_liquid_fraction", fraction)
        elif fraction is not None:
            raise ValidationError(
                f"{where}: 'initial_liquid_fraction' is only allowed when "
                "initial_temp equals melt_point"
            )
        return material

    def specific_enthalpy(self, temp, liquid_fraction=None):
        """Specific enthalpy (J/kg) relative to fully solid at melt point."""
        if temp < self.melt_point:
            return self.cp_solid * (temp - self.melt_point)
        if temp > self.melt_point:
            return self.latent_heat + self.cp_liquid * (temp - self.melt_point)
        fraction = 0.0 if liquid_fraction is None else liquid_fraction
        return self.latent_heat * fraction

    def initial_enthalpy(self):
        return self.mass * self.specific_enthalpy(
            self.initial_temp, self.initial_liquid_fraction
        )


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    materials: tuple = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data, context):
        if not isinstance(data, dict):
            raise ValidationError(f"{context}: experiment must be an object")
        if "id" not in data or "materials" not in data:
            raise ValidationError(f"{context}: need 'id' and 'materials'")
        experiment_id = data["id"]
        if not isinstance(experiment_id, str) or not experiment_id:
            raise ValidationError(f"{context}: 'id' must be a non-empty string")
        where = f"experiment {experiment_id!r}"
        raw_materials = data["materials"]
        if not isinstance(raw_materials, list) or not raw_materials:
            raise ValidationError(f"{where}: 'materials' must be a non-empty list")
        materials = tuple(
            Material.from_dict(item, where) for item in raw_materials
        )
        ids = [m.material_id for m in materials]
        if len(set(ids)) != len(ids):
            raise ValidationError(f"{where}: material ids must be unique")
        melt_points = [m.melt_point for m in materials]
        if len(set(melt_points)) != len(melt_points):
            raise ValidationError(f"{where}: melt points must be distinct")
        return cls(experiment_id=experiment_id, materials=materials)


def parse_experiments(payload):
    """Parse the top-level JSON payload into a list of experiments."""
    if not isinstance(payload, dict) or "experiments" not in payload:
        raise ValidationError("top-level object must contain 'experiments'")
    raw = payload["experiments"]
    if not isinstance(raw, list) or not raw:
        raise ValidationError("'experiments' must be a non-empty list")
    experiments = [
        Experiment.from_dict(item, f"experiments[{index}]")
        for index, item in enumerate(raw)
    ]
    ids = [exp.experiment_id for exp in experiments]
    if len(set(ids)) != len(ids):
        raise ValidationError("experiment ids must be unique")
    return experiments


def _enthalpy_at(materials, temp, melt_fraction=0.0):
    """Total enthalpy at temp; materials melting at temp get melt_fraction."""
    total = 0.0
    for material in materials:
        fraction = melt_fraction if temp == material.melt_point else None
        total += material.mass * material.specific_enthalpy(temp, fraction)
    return total


def _segment_slope(materials, temp):
    """dH/dT in a region with no ongoing phase change at temp."""
    slope = 0.0
    for material in materials:
        cp = (
            material.cp_solid
            if temp < material.melt_point
            else material.cp_liquid
        )
        slope += material.mass * cp
    return slope


def solve_experiment(experiment):
    """Return (equilibrium_temp, {material_id: final_liquid_fraction})."""
    materials = experiment.materials
    target = sum(m.initial_enthalpy() for m in materials)
    melt_points = sorted({m.melt_point for m in materials})

    for melt_point in melt_points:
        low = _enthalpy_at(materials, melt_point, melt_fraction=0.0)
        if target < low:
            slope = _segment_slope(
                materials, math.nextafter(melt_point, -math.inf)
            )
            temp = melt_point - (low - target) / slope
            return temp, _fractions_at(materials, temp)
        high = _enthalpy_at(materials, melt_point, melt_fraction=1.0)
        if target <= high:
            fractions = _fractions_at(materials, melt_point)
            for material in materials:
                if material.melt_point == melt_point:
                    span = material.mass * material.latent_heat
                    fractions[material.material_id] = (
                        (target - low) / span if span else 0.0
                    )
            return melt_point, fractions
    last = melt_points[-1]
    slope = _segment_slope(materials, math.nextafter(last, math.inf))
    temp = last + (target - _enthalpy_at(materials, last, 1.0)) / slope
    return temp, _fractions_at(materials, temp)


def _fractions_at(materials, temp):
    """Liquid fraction of every material at an equilibrium temperature."""
    fractions = {}
    for material in materials:
        if temp < material.melt_point:
            fractions[material.material_id] = 0.0
        elif temp > material.melt_point:
            fractions[material.material_id] = 1.0
        else:
            fractions[material.material_id] = None
    return fractions
