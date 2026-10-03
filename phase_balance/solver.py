"""Equilibrium solver: conserve total enthalpy to find the common temperature."""
from __future__ import annotations

from dataclasses import dataclass

from .model import Experiment


@dataclass(frozen=True)
class MaterialResult:
    material_id: str
    final_temp: float
    final_liquid_fraction: float  # 0.0 solid, 1.0 liquid, partial in between
    initial_enthalpy: float
    final_enthalpy: float

    @property
    def net_heat(self):
        return self.final_enthalpy - self.initial_enthalpy


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    final_temp: float
    initial_enthalpy: float
    final_enthalpy: float
    materials: tuple

    @property
    def residual(self):
        return self.final_enthalpy - self.initial_enthalpy


def _system_enthalpy(experiment, temp, transition=None):
    """Total enthalpy at temp; `transition` is (material, fraction) at its Tm."""
    total = 0.0
    for mat in experiment.materials:
        if transition is not None and mat is transition[0]:
            total += mat.enthalpy(temp, transition[1])
        else:
            total += mat.enthalpy(temp)
    return total


def solve_experiment(experiment: Experiment) -> ExperimentResult:
    mats = experiment.materials
    h_total = sum(m.initial_enthalpy() for m in mats)

    # Knots: for each melting point, system enthalpy just below (solid) and
    # just above (liquid) the transition of that material.
    knots = []
    for mat in sorted(mats, key=lambda m: m.melting_point):
        tm = mat.melting_point
        e_solid = _system_enthalpy(experiment, tm, (mat, 0.0))
        e_liquid = _system_enthalpy(experiment, tm, (mat, 1.0))
        knots.append((tm, mat, e_solid, e_liquid))

    final_temp = None
    transition = None  # (material, fraction)

    for tm, mat, e_solid, e_liquid in knots:
        if e_solid <= h_total <= e_liquid:
            final_temp = tm
            frac = (h_total - e_solid) / (mat.mass * mat.latent_heat)
            transition = (mat, frac)
            break

    if final_temp is None:
        # H lies in a purely sensible-heat segment; solve linearly.
        # Segment bounds: (-inf, knots[0].e_solid), between knots, (last, +inf).
        bounds = [(-float("inf"), None)]
        for tm, mat, e_solid, e_liquid in knots:
            bounds.append((tm, e_liquid))
        # find segment index i where h_total > e_liquid of knot i and
        # h_total < e_solid of knot i+1
        for i in range(len(knots) + 1):
            lo_ok = i == 0 or h_total > knots[i - 1][3]
            hi_ok = i == len(knots) or h_total < knots[i][2]
            if lo_ok and hi_ok:
                break
        # reference point: use nearest knot edge
        if i < len(knots):
            t_ref, e_ref = knots[i][0], knots[i][2]
        else:
            t_ref, e_ref = knots[-1][0], knots[-1][3]
        slope = 0.0
        for mat in mats:
            cp = mat.cp_solid if t_ref < mat.melting_point else mat.cp_liquid
            if t_ref == mat.melting_point:
                # reference sits on this knot's solid edge (i < len) or
                # liquid edge (i == len); pick side consistent with segment
                cp = mat.cp_solid if i < len(knots) else mat.cp_liquid
            slope += mat.mass * cp
        final_temp = t_ref + (h_total - e_ref) / slope

    results = []
    for mat in mats:
        if transition is not None and mat is transition[0]:
            frac = transition[1]
        else:
            # Melting points are distinct, so only the transition material
            # can sit exactly at its melting point here.
            frac = 0.0 if final_temp < mat.melting_point else 1.0
        results.append(
            MaterialResult(
                material_id=mat.material_id,
                final_temp=final_temp,
                final_liquid_fraction=frac,
                initial_enthalpy=mat.initial_enthalpy(),
                final_enthalpy=mat.enthalpy(final_temp, frac)
                if final_temp == mat.melting_point
                else mat.enthalpy(final_temp),
            )
        )
    final_enthalpy = sum(r.final_enthalpy for r in results)
    return ExperimentResult(
        experiment_id=experiment.experiment_id,
        final_temp=final_temp,
        initial_enthalpy=h_total,
        final_enthalpy=final_enthalpy,
        materials=tuple(results),
    )
