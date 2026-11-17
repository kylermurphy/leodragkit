"""Tests for frames (task A4a): types and quaternion conventions (1); the orbit frame and attitude law (2).

The conventions are checked against rotations worked by hand (90° about z), and against a real Spire
quaternion: with D-85's reading, the orbit frame's nadir must lie near body +z (Spire's body frame has +z
towards nadir in nominal pointing).

Run: ``pytest tests/aero/test_frames.py``
"""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from leodragkit.aero.frames import (
    EARTH_ROTATION_RATE_RAD_PER_S,
    Attitude,
    OrbitStates,
    attitude_from_law,
    attitude_from_quaternions,
    inertial_velocity_in_itrf,
    itrf_from_orbit_level,
)

TIMES = np.array(["2023-12-18T09:52:13", "2023-12-18T09:52:14"], dtype="datetime64[ns]")
SIN45, COS45 = np.sin(np.pi / 4), np.cos(np.pi / 4)
QUARTER_TURN_ABOUT_Z = [[0.0, 0.0, SIN45, COS45], [0.0, 0.0, SIN45, COS45]]  # scalar last


def from_quaternions(quaternions, **conventions):
    arguments = {
        "scalar_position": "last",
        "algebra": "hamilton",
        "direction": "body_to_reference",
    } | conventions
    return attitude_from_quaternions(
        TIMES, "GPS", quaternions, frame="orbit_level_spire", source="test", **arguments
    )


# --- the three conventions -------------------------------------------------------------------------


def test_hamilton_body_to_reference_inverts_the_quaternions_rotation():
    # Hamilton u' = q u q* turns body x to reference +y, so body_from_reference turns reference +y to body x.
    attitude = from_quaternions(QUARTER_TURN_ABOUT_Z)
    np.testing.assert_allclose(attitude.body_from_reference.apply([0, 1, 0]), [[1, 0, 0]] * 2, atol=1e-15)


def test_jpl_algebra_turns_the_other_way():
    # The same numbers in JPL algebra turn body x to reference −y.
    attitude = from_quaternions(QUARTER_TURN_ABOUT_Z, algebra="jpl")
    np.testing.assert_allclose(attitude.body_from_reference.apply([0, -1, 0]), [[1, 0, 0]] * 2, atol=1e-15)


def test_scalar_first_is_reordered():
    scalar_first = [[COS45, 0.0, 0.0, SIN45]] * 2
    np.testing.assert_allclose(
        from_quaternions(scalar_first, scalar_position="first").body_from_reference.as_matrix(),
        from_quaternions(QUARTER_TURN_ABOUT_Z).body_from_reference.as_matrix(),
        atol=1e-15,
    )


def test_reference_to_body_keeps_the_quaternions_rotation():
    attitude = from_quaternions(QUARTER_TURN_ABOUT_Z, direction="reference_to_body")
    np.testing.assert_allclose(attitude.body_from_reference.apply([1, 0, 0]), [[0, 1, 0]] * 2, atol=1e-15)


@pytest.mark.parametrize("algebra", ["hamilton", "jpl"])
@pytest.mark.parametrize("direction", ["body_to_reference", "reference_to_body"])
def test_every_combination_recovers_a_known_rotation(algebra, direction):
    # A known body_from_reference, written as each combination of conventions would write it, is recovered.
    known = Rotation.from_rotvec([[0.3, -0.2, 0.9], [0.3, -0.2, 0.9]])
    written = known if direction == "reference_to_body" else known.inv()
    written = written.inv() if algebra == "jpl" else written
    attitude = from_quaternions(written.as_quat(), algebra=algebra, direction=direction)
    np.testing.assert_allclose(attitude.body_from_reference.as_matrix(), known.as_matrix(), atol=1e-14)


def test_a_spire_quaternion_puts_nadir_near_body_z():
    spire = [[-0.0040895075, -0.0001525936, -0.1268052501, 0.9919191909]] * 2  # FM143, 2023-10-31, flag 0
    nadir_in_body = from_quaternions(spire).body_from_reference.apply([0, 0, 1])[0]
    assert np.degrees(np.arccos(nadir_in_body[2])) < 1.0  # 0.47° for this sample


# --- checks ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("quaternions", "conventions", "message"),
    [
        ([[0.0, 0.0, 0.0, 1.1]] * 2, {}, "quaternion 0 has length 1.1"),
        ([[0.0, 0.0, 0.0, np.nan]] * 2, {}, "must be finite"),
        ([[0.0, 0.0, 1.0]] * 2, {}, "shape \\(T, 4\\)"),
        (QUARTER_TURN_ABOUT_Z, {"algebra": "shuster"}, "algebra must be one of"),
        (QUARTER_TURN_ABOUT_Z, {"direction": "body_to_orbit"}, "direction must be one of"),
        (QUARTER_TURN_ABOUT_Z, {"scalar_position": "middle"}, "scalar_position must be one of"),
    ],
)
def test_bad_quaternions_or_conventions_raise(quaternions, conventions, message):
    with pytest.raises(ValueError, match=message):
        from_quaternions(quaternions, **conventions)


def test_an_attitude_checks_its_times_frame_and_rotations():
    rotations = Rotation.identity(2)
    with pytest.raises(ValueError, match="strictly increasing"):
        Attitude(TIMES[::-1], "GPS", rotations, "ITRF", "test")
    with pytest.raises(ValueError, match="time_scale must be one of"):
        Attitude(TIMES, "TAI", rotations, "ITRF", "test")
    with pytest.raises(ValueError, match="frame must be one of"):
        Attitude(TIMES, "GPS", rotations, "LVLH", "test")
    with pytest.raises(ValueError, match="2 times but 3 rotations"):
        Attitude(TIMES, "GPS", Rotation.identity(3), "ITRF", "test")
    with pytest.raises(ValueError, match="one rotation per epoch"):
        Attitude(TIMES, "GPS", Rotation.identity(), "ITRF", "test")


def test_orbit_states_check_their_arrays_and_frame():
    positions = np.array([[6.67e6, 0.0, 0.0], [6.67e6, 7.8e3, 0.0]])
    velocities = np.array([[0.0, 7.8e3, 0.0]] * 2)
    states = OrbitStates(TIMES, "GPS", positions, velocities, "ITRF", "test")
    assert len(states) == 2
    with pytest.raises(ValueError, match="velocities_m_per_s must be finite with shape \\(2, 3\\)"):
        OrbitStates(TIMES, "GPS", positions, velocities[:1], "ITRF", "test")
    with pytest.raises(ValueError, match="frame must be one of"):
        OrbitStates(TIMES, "GPS", positions, velocities, "orbit_level_spire", "test")
    with pytest.raises(ValueError, match="source must be a non-empty string"):
        OrbitStates(TIMES, "GPS", positions, velocities, "ITRF", "")


# --- inertial velocity, the orbit frame, the attitude law (component 2) ------------------------------

R_M = 6.67e6  # about 290 km altitude, as FM134 in December 2023
V_M_PER_S = 7.8e3


def equatorial_states(directions=((0, 1, 0), (0, 1, 0))):
    """Two epochs at (R, 0, 0) in ITRF, moving along the given directions (prograde equatorial by default)."""
    positions = np.array([[R_M, 0.0, 0.0]] * 2)
    velocities = V_M_PER_S * np.array(directions, dtype=float)
    return OrbitStates(TIMES, "GPS", positions, velocities, "ITRF", "test orbit")


def test_the_inertial_velocity_adds_the_earths_rotation_at_the_equator():
    # At (R, 0, 0), ω × r = (0, ωR, 0): about 486 m/s eastward.
    result = inertial_velocity_in_itrf([[R_M, 0.0, 0.0]], [[0.0, 0.0, V_M_PER_S]])
    np.testing.assert_allclose(result, [[0.0, EARTH_ROTATION_RATE_RAD_PER_S * R_M, V_M_PER_S]], rtol=1e-15)
    assert result[0, 1] == pytest.approx(486.4, abs=0.1)


def test_the_inertial_velocity_is_unchanged_over_the_pole():
    np.testing.assert_allclose(
        inertial_velocity_in_itrf([[0.0, 0.0, R_M]], [[V_M_PER_S, 0.0, 0.0]]), [[V_M_PER_S, 0, 0]]
    )


def test_the_orbit_frame_of_a_prograde_equatorial_orbit():
    # r = (R, 0, 0), v = (0, V, 0): Z = (−1, 0, 0) is nadir; Y = −(r × v)/|r × v| = (0, 0, −1);
    # X = Y × Z = (0, 1, 0), along the velocity.
    rotation = itrf_from_orbit_level([[R_M, 0.0, 0.0]], [[0.0, V_M_PER_S, 0.0]])
    np.testing.assert_allclose(rotation.apply([1, 0, 0]), [[0, 1, 0]], atol=1e-15)
    np.testing.assert_allclose(rotation.apply([0, 1, 0]), [[0, 0, -1]], atol=1e-15)
    np.testing.assert_allclose(rotation.apply([0, 0, 1]), [[-1, 0, 0]], atol=1e-15)


def test_the_orbit_frame_is_right_handed_and_points_the_right_way_for_any_state():
    rng = np.random.default_rng(20261103)
    positions = rng.normal(size=(50, 3)) * R_M
    velocities = rng.normal(size=(50, 3)) * V_M_PER_S
    rotation = itrf_from_orbit_level(positions, velocities)
    matrices = rotation.as_matrix()
    np.testing.assert_allclose(np.linalg.det(matrices), 1.0, atol=1e-12)
    x_axis, z_axis = matrices[:, :, 0], matrices[:, :, 2]
    assert np.all(np.einsum("ij,ij->i", z_axis, positions) < 0)  # Z towards the Earth
    assert np.all(np.einsum("ij,ij->i", x_axis, velocities) > 0)  # X along the flight direction


def test_velocity_along_the_position_has_no_orbit_frame():
    with pytest.raises(ValueError, match="0"):
        itrf_from_orbit_level([[R_M, 0.0, 0.0]], [[V_M_PER_S, 0.0, 0.0]])


def flight_direction(states):
    """The orbit frame's X, in ITRF: along the inertial velocity's part perpendicular to r."""
    inertial = inertial_velocity_in_itrf(states.positions_m, states.velocities_m_per_s)
    return itrf_from_orbit_level(states.positions_m, inertial).apply([1, 0, 0])


def test_the_law_points_the_chosen_body_axes_along_the_flight_direction_and_nadir():
    states = equatorial_states()
    attitude = attitude_from_law(states, along_velocity="+x", towards_nadir="+z")
    assert attitude.frame == "ITRF" and attitude.time_scale == "GPS" and len(attitude) == 2
    np.testing.assert_array_equal(attitude.times, states.times)
    # The orbit frame uses the inertial velocity, so X is tilted slightly from the ITRF velocity: check X.
    flight = flight_direction(states)
    np.testing.assert_allclose(attitude.body_from_reference.apply(flight), [[1, 0, 0]] * 2, atol=1e-14)
    np.testing.assert_allclose(
        attitude.body_from_reference.apply([-1, 0, 0]), [[0, 0, 1]] * 2, atol=1e-14
    )  # nadir


def test_grace_leading_flies_with_body_x_against_its_velocity():
    states = equatorial_states()
    attitude = attitude_from_law(states, along_velocity="-x", towards_nadir="+z")
    flight = flight_direction(states)
    np.testing.assert_allclose(attitude.body_from_reference.apply(flight), [[-1, 0, 0]] * 2, atol=1e-14)
    assert np.allclose(np.linalg.det(attitude.body_from_reference.as_matrix()), 1.0)  # still right-handed


@pytest.mark.parametrize(
    ("along", "nadir", "message"),
    [
        ("+x", "+x", "perpendicular"),
        ("+x", "-x", "perpendicular"),
        ("+w", "+z", "must be one of"),
        ("x", "+z", "must be one of"),
    ],
)
def test_the_law_rejects_axes_that_are_not_two_perpendicular_signed_axes(along, nadir, message):
    with pytest.raises(ValueError, match=message):
        attitude_from_law(equatorial_states(), along_velocity=along, towards_nadir=nadir)
