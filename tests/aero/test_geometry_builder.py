"""Tests for primitives and poses (task A3b1): plates, boxes, cylinders, placing, and resolution.

Areas and normals are checked against hand formulas; every closed primitive is checked with trimesh
(skipped when it is not installed) for a watertight, consistently wound surface enclosing the right volume.

Run: ``pytest tests/aero/test_geometry_builder.py``
"""

import numpy as np
import pytest

from leodragkit.aero.geometry import compute_triangle_properties
from leodragkit.aero.geometry_builder import (
    MINIMUM_CYLINDER_SEGMENTS,
    Pose,
    build_box_triangles,
    build_cylinder_triangles,
    build_plate_triangles,
    identity_pose,
    make_pose,
    place_triangles,
)


def longest_edges_m(triangles_m):
    """Longest edge of each triangle."""
    edges = triangles_m[:, [1, 2, 2], :] - triangles_m[:, [0, 0, 1], :]
    return np.linalg.norm(edges, axis=2).max(axis=1)


def assert_closed_and_outward(triangles_m, expected_volume_m3, rel=1e-12):
    """Independent check with trimesh: watertight, consistently wound, enclosing a positive volume."""
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.Trimesh(
        vertices=triangles_m.reshape(-1, 3),
        faces=np.arange(3 * len(triangles_m)).reshape(-1, 3),
        process=True,
    )
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume == pytest.approx(expected_volume_m3, rel=rel)  # positive only if normals point outward


# --- Pose and make_pose -------------------------------------------------------------------------


def test_the_y_axis_is_z_cross_x_so_the_axes_are_right_handed():
    pose = make_pose([0, 0, 0], [0, 1, 0], [1, 0, 0])
    np.testing.assert_allclose(pose.y_axis, [0, 0, 1])
    assert np.linalg.det(pose.rotation_matrix) == pytest.approx(1.0)


def test_rounded_axes_are_made_exact():
    pose = make_pose([0, 0, 0], [1, 0, 0], [0, 0.7071, 0.7071])
    assert np.linalg.norm(pose.z_axis) == pytest.approx(1.0, abs=1e-15)
    np.testing.assert_allclose(pose.rotation_matrix.T @ pose.rotation_matrix, np.eye(3), atol=1e-15)


@pytest.mark.parametrize(
    ("x_axis", "z_axis", "message"),
    [
        ([1.1, 0, 0], [0, 0, 1], "x_axis must have length 1"),
        ([1, 0, 0], [0, 0, 0.9], "z_axis must have length 1"),
        ([1, 0, 0], [0.1, 0, 0.995], "perpendicular"),
        ([1, 0], [0, 0, 1], "x_axis must be three"),
    ],
)
def test_axes_that_are_not_nearly_unit_and_perpendicular_raise(x_axis, z_axis, message):
    with pytest.raises(ValueError, match=message):
        make_pose([0, 0, 0], x_axis, z_axis)


def test_a_pose_built_directly_must_be_exact():
    with pytest.raises(ValueError, match="make_pose"):
        Pose(centre_m=np.zeros(3), x_axis=np.array([1.0, 0, 0]), z_axis=np.array([0, 0.7071, 0.7071]))


# --- place_triangles ----------------------------------------------------------------------------


def test_the_identity_pose_leaves_triangles_unchanged():
    triangles = build_plate_triangles(0.3, 0.1)
    np.testing.assert_allclose(place_triangles(triangles, identity_pose()), triangles)


def test_placing_moves_the_centre_and_turns_the_normal_to_the_pose_z_axis():
    pose = make_pose([1.0, 2.0, 3.0], [0, 1, 0], [1, 0, 0])
    placed = place_triangles(build_plate_triangles(0.3, 0.1), pose)
    properties = compute_triangle_properties(placed)
    np.testing.assert_allclose(properties.outward_normals, [[1, 0, 0]] * len(placed), atol=1e-15)
    np.testing.assert_allclose(placed.reshape(-1, 3).mean(axis=0), [1.0, 2.0, 3.0])
    np.testing.assert_allclose(properties.areas_m2.sum(), 0.03)


def test_placing_maps_the_plates_own_x_to_the_pose_x_axis():
    pose = make_pose([0, 0, 0], [0, 1, 0], [1, 0, 0])
    placed = place_triangles(build_plate_triangles(0.3, 0.1), pose)
    extent = np.ptp(placed.reshape(-1, 3), axis=0)
    np.testing.assert_allclose(extent, [0.0, 0.3, 0.1], atol=1e-15)  # own x (0.3) now along body y


# --- build_plate_triangles ----------------------------------------------------------------------


def test_a_coarse_plate_is_two_triangles_facing_plus_z():
    plate = build_plate_triangles(0.3, 0.1)
    properties = compute_triangle_properties(plate)
    assert plate.shape == (2, 3, 3)
    np.testing.assert_allclose(properties.outward_normals, [[0, 0, 1], [0, 0, 1]])
    assert properties.areas_m2.sum() == pytest.approx(0.03)
    np.testing.assert_allclose(np.ptp(plate.reshape(-1, 3), axis=0), [0.3, 0.1, 0.0])
    np.testing.assert_allclose(plate.reshape(-1, 3).mean(axis=0), [0.0, 0.0, 0.0], atol=1e-15)


def test_a_finer_plate_has_more_cells_and_no_long_edges():
    plate = build_plate_triangles(0.3, 0.1, max_edge_length_m=0.05)
    assert plate.shape == (2 * 6 * 2, 3, 3)  # 6 cells along x, 2 along y
    assert compute_triangle_properties(plate).areas_m2.sum() == pytest.approx(0.03)
    cell_sides = np.abs(
        np.diff(plate[:, [0, 1], :2], axis=1)
    )  # the first edge of each triangle lies along a cell side
    assert np.all(cell_sides <= 0.05 + 1e-12)


def test_a_two_sided_plate_faces_both_ways_with_the_back_after_the_front():
    plate = build_plate_triangles(0.3, 0.1, max_edge_length_m=0.1, two_sided=True)
    normals = compute_triangle_properties(plate).outward_normals
    half = len(plate) // 2
    np.testing.assert_allclose(normals[:half], [[0, 0, 1]] * half)
    np.testing.assert_allclose(normals[half:], [[0, 0, -1]] * half)


@pytest.mark.parametrize(
    ("size_x", "size_y", "max_edge"), [(0.0, 0.1, None), (0.3, -0.1, None), (0.3, 0.1, 0.0)]
)
def test_non_positive_sizes_raise(size_x, size_y, max_edge):
    with pytest.raises(ValueError):
        build_plate_triangles(size_x, size_y, max_edge_length_m=max_edge)


# --- build_box_triangles ------------------------------------------------------------------------


def test_a_box_has_the_right_area_and_every_normal_points_away_from_its_centre():
    box = build_box_triangles(0.1, 0.2, 0.34)
    properties = compute_triangle_properties(box)
    assert box.shape == (12, 3, 3)
    assert properties.areas_m2.sum() == pytest.approx(2 * (0.1 * 0.2 + 0.2 * 0.34 + 0.34 * 0.1))
    assert np.all(np.einsum("ij,ij->i", properties.outward_normals, properties.centroids_m) > 0)
    np.testing.assert_allclose(np.ptp(box.reshape(-1, 3), axis=0), [0.1, 0.2, 0.34])


def test_the_box_faces_come_in_table_order():
    normals = compute_triangle_properties(build_box_triangles(0.1, 0.2, 0.34)).outward_normals[::2]
    np.testing.assert_allclose(
        normals, [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], atol=1e-15
    )


@pytest.mark.parametrize("max_edge", [None, 0.05])
def test_a_box_is_closed_and_wound_outward(max_edge):
    box = build_box_triangles(0.1, 0.2, 0.34, max_edge_length_m=max_edge)
    assert_closed_and_outward(box, expected_volume_m3=0.1 * 0.2 * 0.34)


# --- build_cylinder_triangles -------------------------------------------------------------------


def test_a_coarse_cylinder_has_the_minimum_number_of_segments_and_faceted_areas():
    radius, height = 0.05, 0.4
    cylinder = build_cylinder_triangles(radius, height)
    n = MINIMUM_CYLINDER_SEGMENTS
    assert cylinder.shape == (2 * n + 2 * n, 3, 3)  # side (one row) then two caps
    areas = compute_triangle_properties(cylinder).areas_m2
    side_area = n * 2 * radius * np.sin(np.pi / n) * height  # n flat facets
    cap_area = n * 0.5 * radius**2 * np.sin(2 * np.pi / n)  # n fan triangles
    assert areas[: 2 * n].sum() == pytest.approx(side_area)
    assert areas[2 * n :].sum() == pytest.approx(2 * cap_area)


def test_side_normals_point_radially_outward_and_caps_point_along_z():
    n = MINIMUM_CYLINDER_SEGMENTS
    properties = compute_triangle_properties(build_cylinder_triangles(0.05, 0.4))
    side_normals, side_centroids = properties.outward_normals[: 2 * n], properties.centroids_m[: 2 * n]
    radial = side_centroids[:, :2] / np.linalg.norm(side_centroids[:, :2], axis=1, keepdims=True)
    assert np.all(np.einsum("ij,ij->i", side_normals[:, :2], radial) > 0.9)
    np.testing.assert_allclose(side_normals[:, 2], 0.0, atol=1e-15)
    np.testing.assert_allclose(properties.outward_normals[2 * n : 3 * n], [[0, 0, 1]] * n, atol=1e-15)
    np.testing.assert_allclose(properties.outward_normals[3 * n :], [[0, 0, -1]] * n, atol=1e-15)


def test_a_finer_cylinder_has_short_side_edges_and_more_segments():
    radius, height, max_edge = 0.05, 0.4, 0.02
    cylinder = build_cylinder_triangles(radius, height, max_edge_length_m=max_edge, capped=False)
    segments = int(np.ceil(2 * np.pi * radius / max_edge))
    rows = int(np.ceil(height / max_edge))
    assert cylinder.shape == (2 * segments * rows, 3, 3)
    chord = 2 * radius * np.sin(np.pi / segments)
    assert chord <= max_edge
    assert np.all(longest_edges_m(cylinder) <= np.hypot(chord, height / rows) + 1e-12)  # cell diagonal


def test_an_uncapped_cylinder_is_open_and_a_capped_one_is_closed():
    trimesh = pytest.importorskip("trimesh")
    radius, height, n = 0.05, 0.4, MINIMUM_CYLINDER_SEGMENTS
    open_tube = build_cylinder_triangles(radius, height, capped=False)
    mesh = trimesh.Trimesh(
        open_tube.reshape(-1, 3), np.arange(3 * len(open_tube)).reshape(-1, 3), process=True
    )
    assert not mesh.is_watertight
    prism_volume = n * 0.5 * radius**2 * np.sin(2 * np.pi / n) * height  # the faceted cylinder is a prism
    assert_closed_and_outward(build_cylinder_triangles(radius, height), expected_volume_m3=prism_volume)
