"""Tests for the orientation checks (task A3b3): welding, edges, signed volume, components and the summary.

Correct primitives must pass; deliberately broken shapes must be caught. trimesh, an independent library,
is the oracle for "closed", "consistent" and volume (skipped when it is not installed).

Run: ``pytest tests/aero/test_geometry_checks.py``
"""

import warnings

import numpy as np
import pytest

from leodragkit.aero.geometry import panel_set_from_panels
from leodragkit.aero.geometry_builder import (
    Component,
    build_box_triangles,
    build_cylinder_triangles,
    build_plate_triangles,
    join_components,
    make_pose,
    place_triangles,
)
from leodragkit.aero.geometry_checks import (
    GeometryOrientationWarning,
    check_component,
    check_edges,
    compute_signed_volume_m3,
    summarise_geometry,
    weld_vertices,
)


def box_with_flipped_triangles(indices):
    """A 0.1 × 0.2 × 0.3 m box with the given triangles' corners reversed."""
    triangles = build_box_triangles(0.1, 0.2, 0.3)
    triangles[indices] = triangles[indices][:, ::-1, :]
    return triangles


def plate_beside_bus(two_sided):
    """A 0.3 × 0.1 m plate beside a bus on +y, facing −y (towards the bus) on its front side."""
    pose = make_pose([0.0, 0.25, 0.0], [1, 0, 0], [0, -1, 0])
    return Component(
        "panel", "solar_cell", place_triangles(build_plate_triangles(0.3, 0.1, two_sided=two_sided), pose)
    )


BUS = Component("bus", "aluminium", build_box_triangles(0.1, 0.1, 0.34))


# --- weld_vertices ------------------------------------------------------------------------------


def test_welding_a_box_leaves_its_eight_corners():
    vertices, faces = weld_vertices(build_box_triangles(0.1, 0.2, 0.3))
    assert vertices.shape == (8, 3)
    assert faces.shape == (12, 3)
    np.testing.assert_allclose(vertices[faces], build_box_triangles(0.1, 0.2, 0.3))


def test_nearby_but_distinct_corners_are_not_merged():
    triangles = np.array(
        [[[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[1e-6, 0, 0], [1, 1, 0], [0, 1, 0]]], dtype=float
    )
    vertices, _ = weld_vertices(triangles)
    assert len(vertices) == 5  # (0, 0, 0) and (1e-6, 0, 0) stay apart; (0, 1, 0) is shared


# --- check_edges --------------------------------------------------------------------------------


def test_a_box_is_closed_and_consistent():
    _, faces = weld_vertices(build_box_triangles(0.1, 0.2, 0.3))
    report = check_edges(faces)
    assert report.is_closed and report.is_consistent and report.problem_triangles == ()


def test_one_flipped_triangle_is_inconsistent_and_named():
    _, faces = weld_vertices(box_with_flipped_triangles([0]))
    report = check_edges(faces)
    assert report.is_closed and not report.is_consistent
    assert len(report.problem_triangles) == 2 and 0 in report.problem_triangles


def test_a_box_with_a_face_missing_is_not_closed():
    _, faces = weld_vertices(build_box_triangles(0.1, 0.2, 0.3)[2:])
    assert not check_edges(faces).is_closed


def test_a_flat_plate_is_open_and_consistent():
    _, faces = weld_vertices(build_plate_triangles(0.3, 0.1, max_edge_length_m=0.05))
    report = check_edges(faces)
    assert not report.is_closed and report.is_consistent


# --- compute_signed_volume_m3 -------------------------------------------------------------------


def test_the_signed_volume_of_a_box_is_its_volume():
    assert compute_signed_volume_m3(build_box_triangles(0.1, 0.2, 0.3)) == pytest.approx(0.006, rel=1e-12)


def test_reversing_every_triangle_makes_the_volume_negative():
    assert compute_signed_volume_m3(box_with_flipped_triangles(slice(None))) == pytest.approx(
        -0.006, rel=1e-12
    )


def test_the_signed_volume_does_not_depend_on_where_the_box_is():
    moved = build_box_triangles(0.1, 0.2, 0.3) + np.array([5.0, -3.0, 2.0])
    assert compute_signed_volume_m3(moved) == pytest.approx(0.006, rel=1e-9)


# --- check_component ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "triangles",
    [
        build_box_triangles(0.1, 0.2, 0.3, max_edge_length_m=0.05),
        build_cylinder_triangles(0.05, 0.4, max_edge_length_m=0.05),
    ],
    ids=["box", "capped cylinder"],
)
def test_closed_primitives_pass(triangles):
    check = check_component("part", triangles)
    assert check.is_closed and check.is_consistent and check.signed_volume_m3 > 0
    assert check.status == "ok: closed, outward"


def test_a_flipped_triangle_raises_naming_it():
    with pytest.raises(ValueError, match="flipped"):
        check_component("bus", box_with_flipped_triangles([0]))


def test_an_inside_out_component_raises():
    with pytest.raises(ValueError, match="inward"):
        check_component("bus", box_with_flipped_triangles(slice(None)))


def test_failures_are_reported_not_raised_when_asked():
    check = check_component("bus", box_with_flipped_triangles(slice(None)), raise_on_failure=False)
    assert check.status == "FAIL: normals point inward"


def test_a_two_sided_plate_is_recognised():
    check = check_component("panel", build_plate_triangles(0.3, 0.1, max_edge_length_m=0.05, two_sided=True))
    assert not check.is_closed and check.is_two_sided and check.signed_volume_m3 is None
    assert check.status == "ok: open, two-sided"


@pytest.mark.parametrize(
    "triangles",
    [
        build_box_triangles(0.1, 0.2, 0.3, max_edge_length_m=0.05),
        build_box_triangles(0.1, 0.2, 0.3)[2:],
        build_cylinder_triangles(0.05, 0.4, capped=False),
        build_cylinder_triangles(0.05, 0.4),
    ],
    ids=["box", "box missing a face", "open tube", "capped cylinder"],
)
def test_closed_consistent_and_volume_agree_with_trimesh(triangles):
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.Trimesh(
        triangles.reshape(-1, 3), np.arange(3 * len(triangles)).reshape(-1, 3), process=True
    )
    check = check_component("part", triangles)
    assert check.is_closed == mesh.is_watertight
    assert check.is_consistent == mesh.is_winding_consistent
    if check.is_closed:
        assert check.signed_volume_m3 == pytest.approx(mesh.volume, rel=1e-10)


# --- whole spacecraft: join_components, warnings and the summary --------------------------------


def test_a_correct_spacecraft_joins_without_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error", GeometryOrientationWarning)
        join_components([BUS, plate_beside_bus(two_sided=True)], source="bus and two-sided panel")


def test_a_one_sided_panel_facing_the_bus_warns_naming_it():
    with pytest.warns(GeometryOrientationWarning, match="'panel'"):
        join_components([BUS, plate_beside_bus(two_sided=False)], source="bus and one-sided panel")


def test_an_open_tube_beside_the_body_is_not_flagged():
    # About half a tube's area faces any point off its axis; only a mostly-inward component is flagged.
    boom_pose = make_pose([0.0, 0.3, 0.0], [1, 0, 0], [0, 1, 0])
    boom = Component(
        "boom", "aluminium", place_triangles(build_cylinder_triangles(0.01, 0.4, capped=False), boom_pose)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", GeometryOrientationWarning)
        join_components([BUS, boom], source="bus and boom")


def test_the_warning_is_shown_every_time_not_only_the_first():
    with warnings.catch_warnings(record=True) as caught:
        for _ in range(2):
            join_components([BUS, plate_beside_bus(two_sided=False)], source="twice")
    assert sum(issubclass(warning.category, GeometryOrientationWarning) for warning in caught) == 2


def test_joining_an_inside_out_component_raises():
    inside_out = Component("bus", "aluminium", box_with_flipped_triangles(slice(None)))
    with pytest.raises(ValueError, match="inward"):
        join_components([inside_out], source="broken")


def test_the_summary_has_one_row_per_component_and_shows_as_a_table():
    spacecraft = join_components([BUS, plate_beside_bus(two_sided=True)], source="bus and panel")
    summary = summarise_geometry(spacecraft)
    assert [row["component"] for row in summary.rows()] == ["bus", "panel"]
    assert [row["status"] for row in summary.rows()] == ["ok: closed, outward", "ok: open, two-sided"]
    assert "bus" in str(summary) and "status" in str(summary)
    assert summary._repr_html_().startswith("<table>")


def test_the_summary_shows_failures_and_flags_instead_of_raising():
    with pytest.warns(GeometryOrientationWarning):
        spacecraft = join_components([BUS, plate_beside_bus(two_sided=False)], source="flagged")
    rows = summarise_geometry(spacecraft).rows()
    assert rows[1]["status"].startswith("check:")
    assert 'style="background-color' in summarise_geometry(spacecraft)._repr_html_()


def test_a_macro_model_is_listed_as_not_checkable():
    panels = panel_set_from_panels(
        [[1, 0, 0], [-1, 0, 0]], [0.1, 0.1], [0, 0], [0, 0], ("bus",), ("al",), "table"
    )
    (row,) = summarise_geometry(panels).rows()
    assert row["status"] == "not checkable (no triangles)" and row["triangles"] == 2
