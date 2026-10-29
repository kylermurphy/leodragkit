"""Tests for the Sentman flat plate: structural checks and numerical-precision checks.

The primer's physics reference values (for example Cd = 2.1591 head-on) are not used here: they are
derived, not published, and become test references in task A2 after independent reproduction. The
back-face values below are precision references only: the same formula evaluated in 50-digit
arithmetic (mpmath), to check that the float64 code keeps its digits, not that the physics is right.

Run: ``pytest tests/aero/test_flat_plate.py``
"""

import numpy as np
import pytest

from leodragkit.aero.flat_plate import (
    COOK_REFLECTED_SPEED_CONSTANT,
    KOPPENWALLNER_REFLECTED_SPEED_CONSTANT,
    FlatPlateCoefficients,
    compute_reflected_speed_ratio,
    compute_sentman_flat_plate_coefficients,
)

# Typical conditions near 400 km, as in the primer's test cases.
SPEED_RATIO = 7.0
AMBIENT_TEMPERATURE_KELVIN = 1000.0
WALL_TEMPERATURE_KELVIN = 300.0


def reflected_speed_ratio_for(energy_accommodation, reflected_speed_constant=KOPPENWALLNER_REFLECTED_SPEED_CONSTANT,
                              speed_ratio=SPEED_RATIO):
    """r at the typical conditions above, for the given accommodation, constant and speed ratio."""
    return compute_reflected_speed_ratio(speed_ratio, AMBIENT_TEMPERATURE_KELVIN, WALL_TEMPERATURE_KELVIN,
                                         energy_accommodation, reflected_speed_constant)


def plate(cos_incidence_angle, speed_ratio=SPEED_RATIO, reflected_speed_ratio=None):
    """Coefficients of a plate at the typical conditions, with α = 0.9 unless r is given."""
    if reflected_speed_ratio is None:
        reflected_speed_ratio = reflected_speed_ratio_for(0.9, speed_ratio=speed_ratio)
    return compute_sentman_flat_plate_coefficients(cos_incidence_angle, speed_ratio, reflected_speed_ratio)


# --- Step 2: the reflected-speed ratio ----------------------------------------------------------

def test_at_full_accommodation_both_constants_give_the_wall_temperature_ratio():
    expected = np.sqrt(WALL_TEMPERATURE_KELVIN / (SPEED_RATIO**2 * AMBIENT_TEMPERATURE_KELVIN))
    for constant in (KOPPENWALLNER_REFLECTED_SPEED_CONSTANT, COOK_REFLECTED_SPEED_CONSTANT):
        assert reflected_speed_ratio_for(1.0, constant) == pytest.approx(expected, rel=1e-12)


def test_the_default_constant_is_koppenwallner():
    default = compute_reflected_speed_ratio(SPEED_RATIO, AMBIENT_TEMPERATURE_KELVIN, WALL_TEMPERATURE_KELVIN, 0.9)
    assert default == pytest.approx(reflected_speed_ratio_for(0.9, KOPPENWALLNER_REFLECTED_SPEED_CONSTANT), rel=1e-15)


def test_less_accommodation_means_faster_reemission():
    reflected = reflected_speed_ratio_for(np.array([1.0, 0.9, 0.5, 0.0]))
    assert np.all(np.diff(reflected) > 0)


# --- Step 3: the plate's coefficients -----------------------------------------------------------

def test_the_result_holds_all_three_coefficients_as_arrays():
    coefficients = plate(np.array([1.0, 0.5]))
    assert isinstance(coefficients, FlatPlateCoefficients)
    for values in (coefficients.pressure_coefficient, coefficients.shear_coefficient, coefficients.drag_coefficient):
        assert isinstance(values, np.ndarray) and values.shape == (2,)


def test_drag_is_the_flow_component_of_pressure_and_shear():
    cos_incidence_angle = np.linspace(-1.0, 1.0, 11)
    coefficients = plate(cos_incidence_angle)
    sin_incidence_angle = np.sqrt(1.0 - cos_incidence_angle**2)
    np.testing.assert_allclose(
        coefficients.drag_coefficient,
        coefficients.pressure_coefficient * cos_incidence_angle + coefficients.shear_coefficient * sin_incidence_angle,
        rtol=1e-14, atol=1e-300,
    )


def test_a_head_on_plate_has_no_shear():
    assert plate(1.0).shear_coefficient == 0.0


def test_at_full_accommodation_head_on_drag_does_not_depend_on_the_constant():
    drags = [plate(1.0, reflected_speed_ratio=reflected_speed_ratio_for(1.0, constant)).drag_coefficient
             for constant in (KOPPENWALLNER_REFLECTED_SPEED_CONSTANT, COOK_REFLECTED_SPEED_CONSTANT)]
    assert drags[0] == pytest.approx(drags[1], rel=1e-12)


def test_head_on_drag_grows_as_accommodation_falls():
    drag = plate(1.0, reflected_speed_ratio=reflected_speed_ratio_for(np.array([1.0, 0.9, 0.0]))).drag_coefficient
    assert np.all(np.diff(drag) > 0)


def test_hyperthermal_limit_without_reemission():
    # Large s and r = 0: pressure tends to Newton's 2cos²δ, shear to 2 sinδ cosδ, so drag tends to 2cosδ
    # (Sinpetru et al. 2022a, eqs. 18 and 20, with re-emission removed).
    cos_incidence_angle = np.cos(np.radians([0.0, 30.0, 60.0, 85.0]))
    sin_incidence_angle = np.sin(np.radians([0.0, 30.0, 60.0, 85.0]))
    coefficients = plate(cos_incidence_angle, speed_ratio=1e4, reflected_speed_ratio=0.0)
    np.testing.assert_allclose(coefficients.pressure_coefficient, 2.0 * cos_incidence_angle**2, rtol=1e-6)
    np.testing.assert_allclose(coefficients.shear_coefficient, 2.0 * sin_incidence_angle * cos_incidence_angle,
                               rtol=1e-6, atol=1e-15)
    np.testing.assert_allclose(coefficients.drag_coefficient, 2.0 * cos_incidence_angle, rtol=1e-6)


def test_an_edge_on_plate_has_finite_positive_drag():
    drag = plate(0.0).drag_coefficient
    assert np.isfinite(drag) and drag > 0


# Back-face drag at α = 0.9, T∞ = 1000 K, T_w = 300 K, k = 1/2, r evaluated at each s, from the same
# formula in 50-digit arithmetic (mpmath). Precision references, not physics references.
BACK_FACE_DRAG_50_DIGITS = [
    (1.0, -0.053588952875851978),
    (3.0, -3.8923235862462144e-7),
    (5.0, -7.5964809352652475e-15),
    (7.0, -9.570727352195014e-26),
    (10.0, -2.2056511535500068e-48),
]


@pytest.mark.parametrize(("speed_ratio", "expected_drag"), BACK_FACE_DRAG_50_DIGITS)
def test_a_back_facing_plate_keeps_its_small_negative_drag_to_full_precision(speed_ratio, expected_drag):
    # Molecules striking and leaving the rear face push the plate forward: negative drag, never clipped.
    # Computing 1 + erf(x) instead of erfc(−x) loses these digits, and the sign, from s ≈ 7.
    drag = plate(-1.0, speed_ratio=speed_ratio).drag_coefficient
    assert drag < 0
    assert drag == pytest.approx(expected_drag, rel=1e-12)


def test_inputs_broadcast_and_match_scalar_calls():
    cos_incidence_angle = np.linspace(-1.0, 1.0, 9)
    together = plate(cos_incidence_angle)
    one_at_a_time = [plate(c) for c in cos_incidence_angle]
    for field in ("pressure_coefficient", "shear_coefficient", "drag_coefficient"):
        np.testing.assert_allclose(getattr(together, field), [getattr(single, field) for single in one_at_a_time],
                                   rtol=1e-15, atol=1e-300)


def test_rounding_just_beyond_one_is_clamped():
    just_beyond, exactly_one = plate(1.0 + 1e-15), plate(1.0)
    for field in ("pressure_coefficient", "shear_coefficient", "drag_coefficient"):
        assert getattr(just_beyond, field) == getattr(exactly_one, field)


# --- Invalid inputs raise, naming the input -----------------------------------------------------

@pytest.mark.parametrize(
    ("arguments", "name"),
    [
        ((0.0, 1000.0, 300.0, 0.9), "speed_ratio"),
        ((7.0, -1.0, 300.0, 0.9), "ambient_temperature_kelvin"),
        ((7.0, 1000.0, 0.0, 0.9), "wall_temperature_kelvin"),
        ((7.0, 1000.0, 300.0, 1.1), "energy_accommodation"),
        ((7.0, 1000.0, 300.0, -0.1), "energy_accommodation"),
        ((np.nan, 1000.0, 300.0, 0.9), "speed_ratio"),
        ((7.0, 1000.0, 300.0, 0.9, 0.6), "reflected_speed_constant"),
    ],
)
def test_invalid_reflected_speed_inputs_raise_naming_the_input(arguments, name):
    with pytest.raises(ValueError, match=name):
        compute_reflected_speed_ratio(*arguments)


@pytest.mark.parametrize(
    ("arguments", "name"),
    [
        ((1.1, 7.0, 0.1), "cos_incidence_angle"),
        ((-1.1, 7.0, 0.1), "cos_incidence_angle"),
        ((np.nan, 7.0, 0.1), "cos_incidence_angle"),
        ((1.0, 0.0, 0.1), "speed_ratio"),
        ((1.0, 7.0, -0.1), "reflected_speed_ratio"),
    ],
)
def test_invalid_flat_plate_inputs_raise_naming_the_input(arguments, name):
    with pytest.raises(ValueError, match=name):
        compute_sentman_flat_plate_coefficients(*arguments)
