"""Tests for the Sentman flat plate: structural checks that need no reference numbers.

The primer's numeric reference values (for example Cd = 2.1591 head-on) are not used here: they are
derived, not published, and become test references only after task A2 reproduces them independently.

Run: ``pytest tests/aero/test_flat_plate.py``
"""

import numpy as np
import pytest

from leodragkit.aero.flat_plate import (
    COOK_REFLECTED_SPEED_CONSTANT,
    KOPPENWALLNER_REFLECTED_SPEED_CONSTANT,
    compute_reflected_speed_ratio,
    compute_sentman_flat_plate_drag_coefficient,
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


# --- Step 3: the flat-plate drag coefficient ----------------------------------------------------

def test_at_full_accommodation_head_on_drag_does_not_depend_on_the_constant():
    drags = [compute_sentman_flat_plate_drag_coefficient(1.0, SPEED_RATIO, reflected_speed_ratio_for(1.0, constant))
             for constant in (KOPPENWALLNER_REFLECTED_SPEED_CONSTANT, COOK_REFLECTED_SPEED_CONSTANT)]
    assert drags[0] == pytest.approx(drags[1], rel=1e-12)


def test_head_on_drag_grows_as_accommodation_falls():
    drag = compute_sentman_flat_plate_drag_coefficient(1.0, SPEED_RATIO, reflected_speed_ratio_for(np.array([1.0, 0.9, 0.0])))
    assert np.all(np.diff(drag) > 0)


def test_hyperthermal_limit_without_reemission_absorbs_all_intercepted_momentum():
    # Large s and r = 0: pressure tends to Newton's 2cos²δ and shear to 2 sinδ cosδ, so drag tends to 2cosδ.
    cos_incidence_angle = np.cos(np.radians([0.0, 30.0, 60.0, 85.0]))
    drag = compute_sentman_flat_plate_drag_coefficient(cos_incidence_angle, speed_ratio=1e4, reflected_speed_ratio=0.0)
    np.testing.assert_allclose(drag, 2.0 * cos_incidence_angle, rtol=1e-6)


def test_an_edge_on_plate_has_finite_positive_drag():
    drag = compute_sentman_flat_plate_drag_coefficient(0.0, SPEED_RATIO, reflected_speed_ratio_for(0.9))
    assert np.isfinite(drag) and drag > 0


def test_a_back_facing_plate_is_pushed_forward_more_as_speed_ratio_falls():
    # Molecules striking and leaving the rear face push the plate forward, so its drag is negative.
    # At s = 7 the effect is negligible; it grows as thermal motion catches up with the satellite.
    speed_ratios = np.array([7.0, 3.0, 1.0])
    drag = compute_sentman_flat_plate_drag_coefficient(-1.0, speed_ratios,
                                                       reflected_speed_ratio_for(0.9, speed_ratio=speed_ratios))
    assert abs(drag[0]) < 1e-15
    assert drag[1] < 0 and drag[2] < 0
    assert np.all(np.diff(drag) < 0)


def test_inputs_broadcast_and_match_scalar_calls():
    cos_incidence_angle = np.linspace(-1.0, 1.0, 9)
    reflected = reflected_speed_ratio_for(0.9)
    drag = compute_sentman_flat_plate_drag_coefficient(cos_incidence_angle, SPEED_RATIO, reflected)
    assert drag.shape == (9,)
    one_at_a_time = [compute_sentman_flat_plate_drag_coefficient(c, SPEED_RATIO, reflected) for c in cos_incidence_angle]
    np.testing.assert_allclose(drag, one_at_a_time, rtol=1e-15)


def test_rounding_just_beyond_one_is_clamped():
    reflected = reflected_speed_ratio_for(0.9)
    just_beyond = compute_sentman_flat_plate_drag_coefficient(1.0 + 1e-15, SPEED_RATIO, reflected)
    exactly_one = compute_sentman_flat_plate_drag_coefficient(1.0, SPEED_RATIO, reflected)
    assert just_beyond == exactly_one


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
        compute_sentman_flat_plate_drag_coefficient(*arguments)
