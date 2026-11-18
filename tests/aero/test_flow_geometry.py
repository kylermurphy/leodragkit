"""Tests for the flow on each panel (task A4b): component 1, the PanelFlowGeometry type and its checks.

The geometry is worked by hand for a cube flying +x first (û = −x) plus one plate turned 45°: the +x face
meets the flow squarely (cos δ = 1, no shear), the side faces are edge-on (cos δ = 0, shear along û), the
−x face looks away (cos δ = −1), and the 45° plate has cos δ = sin δ = 1/√2 with its shear along the plate,
downstream.

Run: ``pytest tests/aero/test_flow_geometry.py``
"""

import numpy as np
import pytest

from leodragkit.aero.frames import PanelFlowGeometry

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
