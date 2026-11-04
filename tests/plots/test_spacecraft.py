"""Tests for the 3-D spacecraft plot: smoke tests on the figure object, skipped without plotly.

They check that the right traces exist with the right sizes and names; they cannot check what the figure
looks like. For that, run the tutorial notebook, ``notebooks/aero_tutorial.ipynb``.

Run: ``pytest tests/plots/test_spacecraft.py``
"""

import subprocess
import sys

import numpy as np
import pytest

from leodragkit.aero.geometry import panel_set_from_panels
from leodragkit.plots.spacecraft import (
    BODY_AXIS_TRACE_NAMES,
    NO_POSITIONS_NOTE,
    NORMAL_TIPS_TRACE_NAME,
    NORMALS_TRACE_NAME,
    plot_panel_set_3d,
)


def traces_named(figure, name):
    return [trace for trace in figure.data if trace.name == name]


def mesh_traces(figure):
    return [trace for trace in figure.data if trace.type == "mesh3d"]


@pytest.fixture
def go():
    return pytest.importorskip("plotly.graph_objects")


def test_one_mesh_trace_per_component_named_in_the_legend(go, unit_cube_panel_set):
    figure = plot_panel_set_3d(unit_cube_panel_set)
    assert isinstance(figure, go.Figure)
    assert sorted(trace.name for trace in mesh_traces(figure)) == ["body", "end_caps"]


def test_colouring_by_material_groups_by_material(go, unit_cube_panel_set):
    figure = plot_panel_set_3d(unit_cube_panel_set, color_by="material")
    assert sorted(trace.name for trace in mesh_traces(figure)) == ["aluminium", "solar_cell"]


def test_the_mesh_traces_hold_every_triangle(go, unit_cube_panel_set):
    figure = plot_panel_set_3d(unit_cube_panel_set)
    assert sum(len(trace.i) for trace in mesh_traces(figure)) == unit_cube_panel_set.panel_count


def test_normals_are_one_segment_per_panel_ending_one_normal_length_from_the_centroid(
    go, unit_cube_panel_set
):
    figure = plot_panel_set_3d(unit_cube_panel_set, normal_length_m=0.25)
    (lines,) = traces_named(figure, NORMALS_TRACE_NAME)
    (tips,) = traces_named(figure, NORMAL_TIPS_TRACE_NAME)
    assert len(lines.x) == 3 * unit_cube_panel_set.panel_count  # start, end, None per panel
    expected_tips = unit_cube_panel_set.centroids_m + 0.25 * unit_cube_panel_set.outward_normals
    np.testing.assert_allclose(np.column_stack([tips.x, tips.y, tips.z]), expected_tips)


def test_normals_can_be_hidden(go, unit_cube_panel_set):
    figure = plot_panel_set_3d(unit_cube_panel_set, show_normals=False)
    assert not traces_named(figure, NORMALS_TRACE_NAME) and not traces_named(figure, NORMAL_TIPS_TRACE_NAME)


def test_the_body_axes_are_three_named_traces(go, unit_cube_panel_set):
    figure = plot_panel_set_3d(unit_cube_panel_set)
    assert all(len(traces_named(figure, name)) == 1 for name in BODY_AXIS_TRACE_NAMES)
    figure_without_axes = plot_panel_set_3d(unit_cube_panel_set, show_body_axes=False)
    assert not any(traces_named(figure_without_axes, name) for name in BODY_AXIS_TRACE_NAMES)


def test_a_macro_model_without_positions_draws_normals_from_the_origin_scaled_by_area(go):
    panels = panel_set_from_panels(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [0.04, 0.01], [0, 0], [0, 0], ("bus",), ("aluminium",), "table"
    )
    figure = plot_panel_set_3d(panels)
    assert not mesh_traces(figure)
    (tips,) = traces_named(figure, NORMAL_TIPS_TRACE_NAME)
    tip_lengths = np.linalg.norm(np.column_stack([tips.x, tips.y, tips.z]), axis=1)
    np.testing.assert_allclose(tip_lengths[1] / tip_lengths[0], 0.25)  # areas 0.01 / 0.04
    assert NO_POSITIONS_NOTE in figure.layout.title.text


def test_the_scene_keeps_true_proportions(go, unit_cube_panel_set):
    assert plot_panel_set_3d(unit_cube_panel_set).layout.scene.aspectmode == "data"


def test_traces_are_added_to_a_figure_passed_in(go, unit_cube_panel_set):
    figure = go.Figure()
    returned = plot_panel_set_3d(unit_cube_panel_set, figure=figure)
    assert returned is figure and len(figure.data) > 0


def test_an_unknown_colouring_raises_listing_the_options(go, unit_cube_panel_set):
    with pytest.raises(ValueError, match="component"):
        plot_panel_set_3d(unit_cube_panel_set, color_by="area")


def test_importing_the_module_does_not_load_plotly():
    code = "import sys, leodragkit.plots.spacecraft; print('plotly' in sys.modules)"
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert completed.stdout.strip() == "False"


def test_a_missing_plotly_raises_saying_how_to_install_it(monkeypatch, unit_cube_panel_set):
    monkeypatch.setitem(sys.modules, "plotly", None)
    monkeypatch.setitem(sys.modules, "plotly.graph_objects", None)
    with pytest.raises(ImportError, match="conda install"):
        plot_panel_set_3d(unit_cube_panel_set)
