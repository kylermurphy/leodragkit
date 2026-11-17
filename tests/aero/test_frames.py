"""Tests for frames (task A4a, component 1): the Attitude and OrbitStates types, and quaternion conventions.

The conventions are checked against rotations worked by hand (90° about z), and against a real Spire
quaternion: with D-85's reading, the orbit frame's nadir must lie near body +z (Spire's body frame has +z
towards nadir in nominal pointing).

Run: ``pytest tests/aero/test_frames.py``
"""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from leodragkit.aero.frames import Attitude, OrbitStates, attitude_from_quaternions

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
