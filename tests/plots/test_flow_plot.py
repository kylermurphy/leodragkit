"""Tests for the flow drawn on the spacecraft (task A4b, component 3): plot_flow_on_spacecraft.

The unit cube (tests/conftest.py) flies +x first with its body axes along ITRF's, so the +x face's two
triangles have cos δ = 1, the −x face's −1, and the side faces 0.

Run: ``pytest tests/plots/test_flow_plot.py``
"""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from leodragkit.aero.frames import Attitude, OrbitStates, panel_flow_geometry
from leodragkit.aero.geometry import panel_set_from_panels
from leodragkit.plots.spacecraft import (
    FLOW_TRACE_NAME,
    PANELS_BY_INCIDENCE_TRACE_NAME,
    plot_flow_on_spacecraft,
)

TIMES = np.array(["2023-12-18T09:52:13", "2023-12-18T09:52:14"], dtype="datetime64[ns]")


@pytest.fixture
def go():
    return pytest.importorskip("plotly.graph_objects")


def flying_x(panel_set, velocities=((7.8e3, 0.0, 0.0), (0.0, 7.8e3, 0.0))):
    """The flow on the panels with body axes = ITRF: +x first at the first epoch, +y first at the second."""
    states = OrbitStates(
        TIMES, "GPS", np.tile([0.0, 0.0, -6.67e6], (2, 1)), np.array(velocities), "ITRF", "test"
    )
    attitude = Attitude(TIMES, "GPS", Rotation.identity(2), "ITRF", "body axes = ITRF")
    return panel_flow_geometry(panel_set, attitude, states)


def named(figure, name):
    return [trace for trace in figure.data if trace.name == name]


def test_each_triangle_is_coloured_by_its_cos_on_a_fixed_scale(go, unit_cube_panel_set):
    geometry = flying_x(unit_cube_panel_set)
    (mesh,) = named(plot_flow_on_spacecraft(unit_cube_panel_set, geometry), PANELS_BY_INCIDENCE_TRACE_NAME)
    np.testing.assert_allclose(mesh.intensity, geometry.cos_incidence[0])
    assert mesh.intensitymode == "cell" and (mesh.cmin, mesh.cmax) == (-1.0, 1.0)
    facing = np.round(unit_cube_panel_set.outward_normals[:, 0])  # +1 on the +x face, −1 on −x, 0 elsewhere
    np.testing.assert_allclose(mesh.intensity, facing, atol=1e-12)


def test_another_epoch_colours_another_face(go, unit_cube_panel_set):
    geometry = flying_x(unit_cube_panel_set)
    (mesh,) = named(
        plot_flow_on_spacecraft(unit_cube_panel_set, geometry, epoch_index=1), PANELS_BY_INCIDENCE_TRACE_NAME
    )
    np.testing.assert_allclose(
        mesh.intensity, np.round(unit_cube_panel_set.outward_normals[:, 1]), atol=1e-12
    )


def test_the_flow_arrives_from_upstream_pointing_along_its_direction(go, unit_cube_panel_set):
    geometry = flying_x(unit_cube_panel_set)
    line, cone = named(plot_flow_on_spacecraft(unit_cube_panel_set, geometry), FLOW_TRACE_NAME)
    np.testing.assert_allclose([cone.u[0], cone.v[0], cone.w[0]], [-1, 0, 0])  # the air moves along −x
    assert line.x[0] > line.x[1] > 0  # it comes in from +x, ahead of the spacecraft, towards it


def test_a_macro_model_is_drawn_as_normals_coloured_by_cos(go):
    normals = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0]], dtype=float)
    macro = panel_set_from_panels(
        outward_normals=normals,
        areas_m2=np.array([1.0, 1.0, 2.0]),
        component_ids=np.zeros(3, dtype=int),
        material_ids=np.zeros(3, dtype=int),
        component_names=("body",),
        material_names=("aluminium",),
        source="macro",
    )
    (markers,) = named(plot_flow_on_spacecraft(macro, flying_x(macro)), PANELS_BY_INCIDENCE_TRACE_NAME)
    np.testing.assert_allclose(markers.marker.color, [1, -1, 0], atol=1e-12)


def test_a_geometry_for_other_panels_or_epoch_is_refused(go, unit_cube_panel_set):
    geometry = flying_x(unit_cube_panel_set)
    with pytest.raises(ValueError, match="out of range"):
        plot_flow_on_spacecraft(unit_cube_panel_set, geometry, epoch_index=2)
    fewer = panel_set_from_panels(
        outward_normals=np.array([[1.0, 0.0, 0.0]]),
        areas_m2=np.array([1.0]),
        component_ids=np.zeros(1, dtype=int),
        material_ids=np.zeros(1, dtype=int),
        component_names=("plate",),
        material_names=("aluminium",),
        source="plate",
    )
    with pytest.raises(ValueError, match="1 panels, but the panel set has 12"):
        plot_flow_on_spacecraft(unit_cube_panel_set, flying_x(fewer))
