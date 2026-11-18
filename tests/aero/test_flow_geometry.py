"""Tests for the flow on each panel (task A4b): the type and its checks (1), and computing it (2).

The geometry is worked by hand for a cube flying +x first (û = −x) plus one plate turned 45°: the +x face
meets the flow squarely (cos δ = 1, no shear), the side faces are edge-on (cos δ = 0, shear along û), the
−x face looks away (cos δ = −1), and the 45° plate has cos δ = sin δ = 1/√2 with its shear along the plate,
downstream.

Run: ``pytest tests/aero/test_flow_geometry.py``
"""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from leodragkit.aero.frames import (
    Attitude,
    OrbitStates,
    PanelFlowGeometry,
    attitude_from_law,
    incidence_and_shear,
    panel_flow_geometry,
)
from leodragkit.aero.geometry import panel_set_from_panels

TIMES = np.array(["2023-12-18T09:52:13", "2023-12-18T09:52:14"], dtype="datetime64[ns]")
FLOW = np.array([-1.0, 0.0, 0.0])  # the air moves along −x: the spacecraft flies +x first
ROOT_HALF = np.sqrt(0.5)
# Normals: +x, −x, +y, −y, +z, −z, and a plate turned 45° between +x and +y.
NORMALS = np.array(
    [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1], [ROOT_HALF, ROOT_HALF, 0]]
)
COS_BY_HAND = np.array([1.0, -1.0, 0.0, 0.0, 0.0, 0.0, ROOT_HALF])
SHEAR_BY_HAND = np.array(
    [[0, 0, 0], [0, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-ROOT_HALF, ROOT_HALF, 0]],
    dtype=float,
)


def geometry_arguments():
    """Valid PanelFlowGeometry arguments, the same at both epochs, as a dict to change one field at a time."""
    return {
        "times": TIMES,
        "time_scale": "GPS",
        "speed_m_per_s": np.array([7.8e3, 7.8e3]),
        "flow_direction": np.tile(FLOW, (2, 1)),
        "cos_incidence": np.tile(COS_BY_HAND, (2, 1)),
        "shear_directions": np.tile(SHEAR_BY_HAND, (2, 1, 1)),
        "source": "test attitude and orbit",
    }


def test_the_hand_worked_geometry_is_accepted():
    geometry = PanelFlowGeometry(**geometry_arguments())
    assert len(geometry) == 2 and geometry.panel_count == 7


def test_the_hand_worked_values_follow_the_definitions():
    # cos δ = −n̂ · û, and t̂ = û − (û · n̂) n̂ made unit length, or zero.
    np.testing.assert_allclose(-NORMALS @ FLOW, COS_BY_HAND, atol=1e-15)
    projected = FLOW - (NORMALS @ FLOW)[:, np.newaxis] * NORMALS
    lengths = np.linalg.norm(projected, axis=1)
    unit = lengths[:, np.newaxis] > 1e-12
    by_definition = np.divide(projected, lengths[:, np.newaxis], out=np.zeros_like(projected), where=unit)
    np.testing.assert_allclose(by_definition, SHEAR_BY_HAND, atol=1e-15)


@pytest.mark.parametrize(
    ("field", "change", "message"),
    [
        ("speed_m_per_s", lambda a: a * 0, "must be positive"),
        ("flow_direction", lambda a: a * 2, "flow_direction must be unit vectors"),
        ("cos_incidence", lambda a: a * 1.5, "must lie in \\[−1, 1\\]"),
        ("cos_incidence", lambda a: a[:, :3], "shear_directions must be finite with shape \\(2, 3, 3\\)"),
        ("shear_directions", lambda a: a * 0.5, "unit vectors or zero"),
        ("shear_directions", lambda a: -a, "û · t̂ should equal sin δ"),
        ("speed_m_per_s", lambda a: np.array([7.8e3, np.nan]), "speed_m_per_s must be finite"),
        ("source", lambda a: "", "source must be a non-empty string"),
    ],
    ids=[
        "zero speed",
        "flow not unit",
        "cos above 1",
        "panel counts differ",
        "shear half length",
        "shear upstream",
        "speed not finite",
        "no source",
    ],
)
def test_inconsistent_geometry_raises_naming_the_field(field, change, message):
    arguments = geometry_arguments()
    arguments[field] = change(arguments[field])
    with pytest.raises(ValueError, match=message):
        PanelFlowGeometry(**arguments)


def test_times_are_checked_as_everywhere_in_aero():
    arguments = geometry_arguments() | {"times": TIMES[::-1]}
    with pytest.raises(ValueError, match="strictly increasing"):
        PanelFlowGeometry(**arguments)


# --- incidence_and_shear and panel_flow_geometry (component 2) ----------------------------------------


def test_the_hand_worked_cube_and_plate_are_reproduced():
    cos_incidence, shear = incidence_and_shear(NORMALS, np.tile(FLOW, (2, 1)))
    np.testing.assert_allclose(cos_incidence, np.tile(COS_BY_HAND, (2, 1)), atol=1e-15)
    np.testing.assert_allclose(shear, np.tile(SHEAR_BY_HAND, (2, 1, 1)), atol=1e-15)


def test_normals_per_epoch_give_the_same_answer_as_fixed_normals():
    # D-88: (T, N, 3) normals, the same at every epoch, must match (N, 3).
    flows = np.array([FLOW, [0.0, -1.0, 0.0]])
    fixed = incidence_and_shear(NORMALS, flows)
    per_epoch = incidence_and_shear(np.tile(NORMALS, (2, 1, 1)), flows)
    for a, b in zip(fixed, per_epoch, strict=True):
        np.testing.assert_allclose(a, b, atol=1e-15)


def test_normals_that_move_between_epochs_are_used_epoch_by_epoch():
    # At the second epoch every panel is turned round (normals negated): every cos δ changes sign.
    moving = np.stack([NORMALS, -NORMALS])
    cos_incidence, _ = incidence_and_shear(moving, np.tile(FLOW, (2, 1)))
    np.testing.assert_allclose(cos_incidence[1], -cos_incidence[0], atol=1e-15)


def test_turning_the_panels_about_the_flow_keeps_every_cos_and_turns_every_shear():
    # Turning a body about the flow direction cannot change how squarely the flow meets any panel.
    rng = np.random.default_rng(20261104)
    normals = rng.normal(size=(40, 3))
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    turn = Rotation.from_rotvec(0.7 * FLOW)  # 0.7 rad about the flow axis
    flow = FLOW[np.newaxis, :]
    cos_before, shear_before = incidence_and_shear(normals, flow)
    cos_after, shear_after = incidence_and_shear(turn.apply(normals), flow)
    np.testing.assert_allclose(cos_after, cos_before, atol=1e-14)
    np.testing.assert_allclose(shear_after[0], turn.apply(shear_before[0]), atol=1e-14)


def test_shear_is_on_the_panel_and_unit_or_zero_for_random_flows():
    rng = np.random.default_rng(4)
    normals = rng.normal(size=(30, 3))
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    flows = rng.normal(size=(20, 3))
    flows /= np.linalg.norm(flows, axis=1, keepdims=True)
    cos_incidence, shear = incidence_and_shear(normals, flows)
    np.testing.assert_allclose(
        np.einsum("tnk,nk->tn", shear, normals), 0.0, atol=1e-14
    )  # in the panel's plane
    np.testing.assert_allclose(
        np.linalg.norm(shear, axis=2), 1.0, atol=1e-12
    )  # no flow is along a normal here
    np.testing.assert_allclose(
        np.einsum("tk,tnk->tn", flows, shear), np.sqrt(1 - cos_incidence**2), atol=1e-12
    )


# A spacecraft whose body axes are ITRF's (identity attitude) flying along +x in ITRF: the flow is −x.

CUBE_AND_PLATE = panel_set_from_panels(
    outward_normals=NORMALS,
    areas_m2=np.ones(7),
    component_ids=np.zeros(7, dtype=int),
    material_ids=np.zeros(7, dtype=int),
    component_names=("cube and plate",),
    material_names=("aluminium",),
    source="test",
)


def states_flying_x(times=TIMES, speeds=(7.8e3, 7.8e3)):
    count = len(times)
    velocities = np.column_stack([np.array(speeds, dtype=float), np.zeros(count), np.zeros(count)])
    positions = np.tile([0.0, -6.67e6, 0.0], (count, 1))
    return OrbitStates(times, "GPS", positions, velocities, "ITRF", "test orbit")


def identity_attitude(times=TIMES, frame="ITRF"):
    return Attitude(times, "GPS", Rotation.identity(len(times)), frame, "body axes = ITRF")


def test_the_whole_calculation_reproduces_the_hand_worked_geometry():
    geometry = panel_flow_geometry(CUBE_AND_PLATE, identity_attitude(), states_flying_x())
    np.testing.assert_allclose(geometry.flow_direction, np.tile(FLOW, (2, 1)), atol=1e-15)
    np.testing.assert_allclose(geometry.speed_m_per_s, [7.8e3, 7.8e3])
    np.testing.assert_allclose(geometry.cos_incidence, np.tile(COS_BY_HAND, (2, 1)), atol=1e-15)
    np.testing.assert_allclose(geometry.shear_directions, np.tile(SHEAR_BY_HAND, (2, 1, 1)), atol=1e-15)
    np.testing.assert_array_equal(geometry.times, TIMES)
    assert geometry.time_scale == "GPS" and geometry.source


def test_the_attitude_turns_the_flow_into_the_body_frame():
    # Under the law (+x along the inertial flight direction), +x is almost square to the flow: cos δ just
    # below 1, because the air's direction differs from the inertial one by the Earth's rotation (degrees).
    positions = np.tile([6.67e6, 0.0, 0.0], (2, 1))
    velocities = np.tile([0.0, 0.0, 7.8e3], (2, 1))  # over the equator, going north: a polar orbit
    states = OrbitStates(TIMES, "GPS", positions, velocities, "ITRF", "polar orbit")
    geometry = panel_flow_geometry(
        CUBE_AND_PLATE, attitude_from_law(states, along_velocity="+x", towards_nadir="+z"), states
    )
    earth_rotation_angle = np.arctan2(7.292115e-5 * 6.67e6, 7.8e3)  # ωR against V, about 3.6°
    np.testing.assert_allclose(geometry.cos_incidence[:, 0], np.cos(earth_rotation_angle), atol=1e-9)


def test_a_slice_of_epochs_gives_the_same_rows():
    # What makes chunking in A5 safe (D-88).
    times = TIMES[0] + np.arange(6) * np.timedelta64(1, "s")
    turns = Rotation.from_rotvec(
        np.column_stack([np.linspace(0, 1, 6), np.linspace(0, -0.5, 6), np.zeros(6)])
    )
    attitude = Attitude(times, "GPS", turns, "ITRF", "turning")
    states = states_flying_x(times, speeds=np.linspace(7.7e3, 7.9e3, 6))
    full = panel_flow_geometry(CUBE_AND_PLATE, attitude, states)
    part = panel_flow_geometry(
        CUBE_AND_PLATE,
        Attitude(times[2:5], "GPS", turns[2:5], "ITRF", "turning"),
        states_flying_x(times[2:5], speeds=np.linspace(7.7e3, 7.9e3, 6)[2:5]),
    )
    np.testing.assert_array_equal(part.cos_incidence, full.cos_incidence[2:5])
    np.testing.assert_array_equal(part.shear_directions, full.shear_directions[2:5])


def test_an_attitude_not_in_itrf_is_refused():
    with pytest.raises(ValueError, match="ITRF"):
        panel_flow_geometry(CUBE_AND_PLATE, identity_attitude(frame="orbit_level_spire"), states_flying_x())


def test_different_epochs_are_refused():
    with pytest.raises(ValueError, match="common_epochs"):
        panel_flow_geometry(
            CUBE_AND_PLATE, identity_attitude(TIMES + np.timedelta64(1, "s")), states_flying_x()
        )


def test_zero_speed_is_refused_naming_the_epoch():
    with pytest.raises(ValueError, match="epoch 1"):
        panel_flow_geometry(CUBE_AND_PLATE, identity_attitude(), states_flying_x(speeds=(7.8e3, 0.0)))
