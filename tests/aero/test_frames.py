"""Tests for frames (task A4a): conventions (1); orbit frame and law (2); ITRF and shared epochs (3).

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
    attitude_in_itrf,
    check_same_epochs,
    common_epochs,
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


# --- the orbit level frame into ITRF, and shared epochs (component 3) --------------------------------


def spire_attitude(quaternion, times=TIMES):
    """A Spire-style attitude (body to orbit level frame, Hamilton, scalar last), the same at every epoch."""
    return attitude_from_quaternions(
        times,
        "GPS",
        [quaternion] * len(times),
        scalar_position="last",
        algebra="hamilton",
        direction="body_to_reference",
        frame="orbit_level_spire",
        source="spire-style test",
    )


def test_a_body_aligned_with_the_orbit_frame_is_the_law_with_x_ahead_and_z_down():
    states = equatorial_states()
    turned = attitude_in_itrf(spire_attitude([0.0, 0.0, 0.0, 1.0]), states)
    law = attitude_from_law(states, along_velocity="+x", towards_nadir="+z")
    assert turned.frame == "ITRF" and "orbit frame from test orbit" in turned.source
    np.testing.assert_allclose(
        turned.body_from_reference.as_matrix(), law.body_from_reference.as_matrix(), atol=1e-14
    )


def test_a_half_turn_in_yaw_is_the_law_flying_backwards():
    # A 180° turn about the orbit Z (nadir) axis puts body x against the flight direction: GRACE leading.
    states = equatorial_states()
    turned = attitude_in_itrf(spire_attitude([0.0, 0.0, 1.0, 0.0]), states)
    law = attitude_from_law(states, along_velocity="-x", towards_nadir="+z")
    np.testing.assert_allclose(
        turned.body_from_reference.as_matrix(), law.body_from_reference.as_matrix(), atol=1e-14
    )


def test_an_attitude_already_in_itrf_is_returned_as_it_is():
    states = equatorial_states()
    law = attitude_from_law(states, along_velocity="+x", towards_nadir="+z")
    assert attitude_in_itrf(law, states) is law


def test_different_epochs_raise_and_point_to_common_epochs():
    states = equatorial_states()
    later = TIMES + np.timedelta64(1, "s")  # 09:52:14 and 09:52:15: one shared with the states
    with pytest.raises(ValueError, match="1 are shared. common_epochs"):
        attitude_in_itrf(spire_attitude([0.0, 0.0, 0.0, 1.0], times=later), states)
    with pytest.raises(ValueError, match="one scale"):
        check_same_epochs(Attitude(TIMES, "UTC", Rotation.identity(2), "orbit_level_spire", "test"), states)


def test_common_epochs_keeps_only_the_shared_epochs_with_their_own_data():
    states = equatorial_states(
        directions=((0, 1, 0), (0, 0, 1))
    )  # 09:52:13 and 09:52:14, different velocities
    times = np.array(["2023-12-18T09:52:12", "2023-12-18T09:52:14"], dtype="datetime64[ns]")
    attitude = attitude_from_quaternions(
        times,
        "GPS",
        [[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 0.0]],
        scalar_position="last",
        algebra="hamilton",
        direction="body_to_reference",
        frame="orbit_level_spire",
        source="test",
    )
    kept_attitude, kept_states = common_epochs(attitude, states)
    np.testing.assert_array_equal(kept_attitude.times, [np.datetime64("2023-12-18T09:52:14", "ns")])
    np.testing.assert_array_equal(kept_states.times, kept_attitude.times)
    np.testing.assert_allclose(kept_states.velocities_m_per_s, [[0, 0, V_M_PER_S]])  # the 09:52:14 state
    # The 09:52:14 attitude, a half turn about z (q and −q are the same rotation, so compare matrices).
    np.testing.assert_allclose(
        kept_attitude.body_from_reference.as_matrix(), [np.diag([-1.0, -1.0, 1.0])], atol=1e-15
    )


def test_common_epochs_raises_when_nothing_is_shared_or_the_scales_differ():
    states = equatorial_states()
    with pytest.raises(ValueError, match="share no epoch"):
        common_epochs(spire_attitude([0.0, 0.0, 0.0, 1.0], times=TIMES + np.timedelta64(1, "h")), states)
    with pytest.raises(ValueError, match="one scale"):
        common_epochs(Attitude(TIMES, "UTC", Rotation.identity(2), "orbit_level_spire", "test"), states)
