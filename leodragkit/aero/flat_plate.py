"""Pressure, shear and drag coefficients of one flat plate in free-molecular flow (Sentman).

The building block of the panel method: a satellite is a set of flat plates, and its force is the
area-weighted sum of each plate's pressure and shear. This module covers one plate:

1. ``compute_reflected_speed_ratio``: how fast molecules leave the surface, relative to how fast
   they arrived, given the energy accommodation coefficient.
2. ``compute_sentman_flat_plate_coefficients``: the plate's pressure, shear and drag coefficients,
   given the angle between its outward normal and the flow, the speed ratio and the
   reflected-speed ratio.

Conventions:

- cos δ = n̂_outward · v̂_rel, with v̂_rel the satellite's velocity relative to the co-rotating
  atmosphere. δ = 0 faces straight into the flow; δ > 90° faces backward.
- The flow direction is −v̂_rel, the direction the molecules travel relative to the satellite.
  Pressure pushes into the plate, along −n̂_outward. Shear acts along t̂, the flow direction
  projected onto the plate and normalised. The plate's force is q·A·(C_p·(−n̂_outward) + C_τ·t̂),
  with q = ½ρV², so its component along the flow is C_d = C_p cos δ + C_τ sin δ.
- Coefficients are referenced to the plate's own area. A back-facing plate has a small negative
  drag (molecules striking and leaving its rear face push it forward); it is never clipped.
- The speed ratio uses the most probable thermal speed: s = V / sqrt(2 k_B T∞ / m).

Method: ``docs/methods/drag_coefficient_primer.md``, steps 2–3.

Sources:

- Sinpetru, L. A., Crisp, N. H., Mostaza-Prieto, D., Livadiotti, S., & Roberts, P. C. E. (2022).
  ADBSat: Methodology of a novel panel method tool for aerodynamic analysis of satellites.
  Computer Physics Communications, 275, 108326. doi:10.1016/j.cpc.2022.108326
  Equation numbers below are those of the preprint, arXiv:2104.05543v2, which may differ from the
  journal version: eqs. 6–7, the Sentman pressure and shear coefficients; eq. 25, the incidence angle.
  The preprint's eq. 6 has a bracket typo: the re-emission term is α(T_w/T_i − 1), not αT_w/(T_i − 1).
- Moe, K., & Moe, M. M. (2005). Gas–surface interactions and satellite drag coefficients.
  Planetary and Space Science, 53, 793–801. doi:10.1016/j.pss.2005.03.005

Read first: ``compute_reflected_speed_ratio``.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy.special import erfc

# The two conventions for the reflected-speed constant k. Sentman uses 1/2 by default; DRIA uses 2/3.
KOPPENWALLNER_REFLECTED_SPEED_CONSTANT = 0.5  # used by the ADBSat code; the Sentman default, so results compare with it
COOK_REFLECTED_SPEED_CONSTANT = 2.0 / 3.0  # used by Cook, Moe & Moe, and the published DRIA

# Dot products of unit vectors can overshoot ±1 by rounding (about 1e-16). Values within this
# tolerance are clamped to ±1; anything further out is an error in the caller's geometry.
COS_INCIDENCE_TOLERANCE = 1e-12


@dataclass(frozen=True)
class FlatPlateCoefficients:
    """Coefficients of one flat plate, referenced to its own area; arrays broadcast over the inputs.

    The plate's force is q·A·(pressure_coefficient·(−n̂_outward) + shear_coefficient·t̂), where t̂ is
    the flow direction projected onto the plate (see the module docstring).
    """

    pressure_coefficient: np.ndarray  # C_p: pushes into the plate, along −n̂_outward
    shear_coefficient: np.ndarray  # C_τ: along the flow direction projected onto the plate
    drag_coefficient: np.ndarray  # C_d = C_p cos δ + C_τ sin δ: the component along the flow


def compute_reflected_speed_ratio(
    speed_ratio: ArrayLike,
    ambient_temperature_kelvin: ArrayLike,
    wall_temperature_kelvin: ArrayLike,
    energy_accommodation: ArrayLike,
    reflected_speed_constant: float = KOPPENWALLNER_REFLECTED_SPEED_CONSTANT,
) -> np.ndarray:
    """Return r, the ratio of re-emitted to incoming molecular speed.

    Method: ``docs/methods/drag_coefficient_primer.md``, step 2.

    Accommodation is defined on energies, α = (E_i − E_r) / (E_i − E_w). It becomes a speed ratio

        r = V_r / V_i = sqrt( k [1 + α (T_w / T_i − 1)] ),

    where T_i is the incident temperature. Both conventions give T_i = k s² T∞:

        Koppenwallner (k = 1/2): T_i = m V² / (4 k_B) = (1/2) s² T∞
        Cook, Moe     (k = 2/3): T_i = m V² / (3 k_B) = (2/3) s² T∞

    using s² = m V² / (2 k_B T∞). At α = 1 both reduce to r = sqrt(T_w / (s² T∞)).

    Parameters
    ----------
    speed_ratio
        s, the satellite speed relative to the atmosphere over the most probable thermal speed; > 0.
    ambient_temperature_kelvin
        T∞, the gas temperature; > 0.
    wall_temperature_kelvin
        T_w, the surface temperature; > 0. No default: it is an explicit modelling choice.
    energy_accommodation
        α, in [0, 1]; 1 means the re-emitted molecules leave at the wall temperature. No default.
    reflected_speed_constant
        k: ``KOPPENWALLNER_REFLECTED_SPEED_CONSTANT`` (1/2, the default) or
        ``COOK_REFLECTED_SPEED_CONSTANT`` (2/3). Must be written to every output.

    Returns
    -------
    np.ndarray
        r, float64, broadcast over the inputs.

    Raises
    ------
    ValueError
        If an input is not finite or out of range, or k is neither constant. The message names the input.

    Example::

        r = compute_reflected_speed_ratio(7.0, 1000.0, 300.0, energy_accommodation=0.9)
    """
    # 1. Check the inputs with _as_checked_array, and check k is one of the two constants.
    # 2. Incident temperature: T_i = k s² T∞.
    # 3. Reflected-speed ratio: r = sqrt(k [1 + α (T_w / T_i − 1)]).
    raise NotImplementedError(
        "compute_reflected_speed_ratio: follow the numbered steps; np.sqrt and numpy broadcasting do the rest."
    )


def compute_sentman_flat_plate_coefficients(
    cos_incidence_angle: ArrayLike,
    speed_ratio: ArrayLike,
    reflected_speed_ratio: ArrayLike,
) -> FlatPlateCoefficients:
    """Return the pressure, shear and drag coefficients of one diffuse flat plate.

    Method: ``docs/methods/drag_coefficient_primer.md``, step 3.

    With c = cos δ, sin δ = sqrt(1 − c²), E = exp(−s² c²) and F = 1 + erf(s c) = erfc(−s c):

        C_p = (c² + 1/(2 s²)) F + c / (s sqrt(π)) E + (r/2) [sqrt(π) c F + E / s]
        C_τ = sin δ · c · F + sin δ / (s sqrt(π)) E
        C_d = C_p cos δ + C_τ sin δ

    Compute F as erfc(−s c), never as 1 + erf(s c): on a back face s c is large and negative, erf is
    almost exactly −1, and the subtraction loses every digit. At s = 7 the erf form even gets the sign
    of the back-face drag wrong, while erfc matches 50-digit arithmetic to about 1e-13.

    Parameters
    ----------
    cos_incidence_angle
        cos δ = n̂_outward · v̂_rel, in [−1, 1]. Values beyond ±1 by up to ``COS_INCIDENCE_TOLERANCE``
        (rounding) are clamped; anything further raises.
    speed_ratio
        s; > 0.
    reflected_speed_ratio
        r from ``compute_reflected_speed_ratio``; ≥ 0. Taken as an input so the two steps stay
        separate and tests can set r = 0 (no re-emission).

    Returns
    -------
    FlatPlateCoefficients
        C_p, C_τ and C_d as float64 arrays, broadcast over the inputs.

    Raises
    ------
    ValueError
        If an input is not finite or out of range. The message names the input.

    Example::

        r = compute_reflected_speed_ratio(7.0, 1000.0, 300.0, energy_accommodation=0.9)
        head_on = compute_sentman_flat_plate_coefficients(1.0, 7.0, r)
        head_on.drag_coefficient
    """
    # 1. Check the inputs; clamp cos δ to [−1, 1] when it overshoots by no more than the tolerance.
    # 2. sin δ from cos δ (δ is in [0, π], so sin δ ≥ 0).
    # 3. The shared terms E and F, with F from erfc.
    # 4. Pressure coefficient C_p.
    # 5. Shear coefficient C_τ.
    # 6. Drag coefficient: the components of C_p and C_τ along the flow.
    raise NotImplementedError(
        "compute_sentman_flat_plate_coefficients: follow the numbered steps; "
        "scipy.special.erfc, np.exp and np.sqrt are all you need."
    )


def _as_checked_array(
    name: str,
    values: ArrayLike,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_is_allowed: bool = True,
) -> np.ndarray:
    """Return ``values`` as a float64 array; raise ValueError naming ``name`` if any is out of range.

    ``minimum_is_allowed=False`` makes the lower bound strict (for inputs that must be > minimum).
    The error message names the input and the bound it broke, so the caller knows what to fix.

    Example::

        speed_ratio = _as_checked_array("speed_ratio", 7.0, minimum=0.0, minimum_is_allowed=False)
    """
    # 1. Convert to a float64 array, so scalars, lists and arrays are handled alike.
    array = np.asarray(values, dtype=float)

    # 2. Every value must be finite: NaN or infinity means a bad input upstream.
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite, got {values!r}.")

    # 3. Check the lower bound (strict when the minimum itself is not allowed), then the upper bound.
    if minimum is not None:
        below = array < minimum if minimum_is_allowed else array <= minimum
        if np.any(below):
            bound = f">= {minimum}" if minimum_is_allowed else f"> {minimum}"
            raise ValueError(f"{name} must be {bound}, got {values!r}.")
    if maximum is not None and np.any(array > maximum):
        raise ValueError(f"{name} must be <= {maximum}, got {values!r}.")
    return array
