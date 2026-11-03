"""Tests for the PanelSet: triangle maths, the two constructors and validation.

Hand-checkable shapes first (one triangle, a unit cube), then random triangles against trimesh, an
independent library used only in tests and skipped when it is not installed.

Run: ``pytest tests/aero/test_geometry.py``
"""

import numpy as np
import pytest

from leodragkit.aero.geometry import (
    PanelSet,
    compute_triangle_properties,
    panel_set_from_panels,
    panel_set_from_triangles,
)

RIGHT_TRIANGLE_M = np.array(
    [[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]]
)  # counter-clockwise from +z


def unit_cube_triangles_m():
    """The 12 triangles of a unit cube centred on the origin, each counter-clockwise seen from outside."""
    corners = np.array(
        [[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
    )  # index = 4·(x > 0) + 2·(y > 0) + (z > 0)
    faces = [  # each face as four corners, counter-clockwise seen from outside, split into two triangles
        (0, 1, 3, 2),  # −x
        (4, 6, 7, 5),  # +x
        (0, 4, 5, 1),  # −y
        (2, 3, 7, 6),  # +y
        (0, 2, 6, 4),  # −z
        (1, 5, 7, 3),  # +z
    ]
    triangles = []
    for a, b, c, d in faces:
        triangles += [corners[[a, b, c]], corners[[a, c, d]]]
    return np.array(triangles)


# --- compute_triangle_properties ----------------------------------------------------------------


def test_a_right_triangle_has_the_expected_normal_area_and_centroid():
    properties = compute_triangle_properties(RIGHT_TRIANGLE_M)
    np.testing.assert_allclose(properties.outward_normals, [[0.0, 0.0, 1.0]])
    np.testing.assert_allclose(properties.areas_m2, [0.5])
    np.testing.assert_allclose(properties.centroids_m, [[1 / 3, 1 / 3, 0.0]])


def test_reversing_the_corner_order_flips_the_normal():
    reversed_order = RIGHT_TRIANGLE_M[:, ::-1, :]
    np.testing.assert_allclose(
        compute_triangle_properties(reversed_order).outward_normals, [[0.0, 0.0, -1.0]]
    )


def test_a_unit_cube_has_area_six_and_every_normal_points_away_from_its_centre():
    properties = compute_triangle_properties(unit_cube_triangles_m())
    assert properties.areas_m2.shape == (12,)
    assert properties.areas_m2.sum() == pytest.approx(6.0, rel=1e-14)
    outward = np.einsum("ij,ij->i", properties.outward_normals, properties.centroids_m)
    assert np.all(outward > 0)
    face_normals = {tuple(np.round(normal).astype(int)) for normal in properties.outward_normals}
    assert face_normals == {(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)}


def test_scaling_a_triangle_by_two_quadruples_its_area():
    properties = compute_triangle_properties(2.0 * RIGHT_TRIANGLE_M)
    np.testing.assert_allclose(properties.areas_m2, [2.0])
    np.testing.assert_allclose(properties.outward_normals, [[0.0, 0.0, 1.0]])


@pytest.mark.parametrize(
    "triangle",
    [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],  # collinear corners
        [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],  # repeated corner
    ],
)
def test_a_degenerate_triangle_raises_with_its_index(triangle):
    triangles = np.array([RIGHT_TRIANGLE_M[0], triangle])
    with pytest.raises(ValueError, match="1"):
        compute_triangle_properties(triangles)


@pytest.mark.parametrize(
    "bad_vertices",
    [np.zeros((2, 3)), np.zeros((2, 4, 3)), np.full((1, 3, 3), np.nan)],
)
def test_a_badly_shaped_or_non_finite_array_raises(bad_vertices):
    with pytest.raises(ValueError, match="triangle_vertices_m"):
        compute_triangle_properties(bad_vertices)


def test_random_triangles_match_trimesh():
    trimesh = pytest.importorskip("trimesh")
    rng = np.random.default_rng(20261030)
    triangles = rng.uniform(-1.0, 1.0, size=(200, 3, 3))
    properties = compute_triangle_properties(triangles)
    np.testing.assert_allclose(properties.areas_m2, trimesh.triangles.area(triangles), rtol=1e-12)
    expected_normals, valid = trimesh.triangles.normals(triangles)
    assert np.all(valid)
    np.testing.assert_allclose(properties.outward_normals, expected_normals, rtol=1e-10, atol=1e-12)


# --- panel_set_from_triangles -------------------------------------------------------------------


def test_a_panel_set_from_triangles_carries_positions_and_corners():
    panels = panel_set_from_triangles(
        unit_cube_triangles_m(),
        np.zeros(12, dtype=int),
        np.zeros(12, dtype=int),
        ("bus",),
        ("aluminium",),
        "cube",
    )
    assert panels.panel_count == 12
    assert panels.has_positions and panels.has_triangles
    assert panels.areas_m2.sum() == pytest.approx(6.0)


def test_components_and_materials_are_kept_per_panel():
    triangles = np.concatenate([RIGHT_TRIANGLE_M, RIGHT_TRIANGLE_M + [0.0, 0.0, 1.0]])
    panels = panel_set_from_triangles(
        triangles, [0, 1], [1, 0], ("bus", "panel"), ("aluminium", "solar_cell"), "two"
    )
    assert [panels.component_names[i] for i in panels.component_ids] == ["bus", "panel"]
    assert [panels.material_names[i] for i in panels.material_ids] == ["solar_cell", "aluminium"]


# --- panel_set_from_panels (macro models) -------------------------------------------------------


def test_a_macro_model_without_positions_is_accepted_but_says_so():
    panels = panel_set_from_panels(
        [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]], [0.03, 0.03], [0, 0], [0, 0], ("bus",), ("aluminium",), "table"
    )
    assert panels.panel_count == 2
    assert not panels.has_positions and not panels.has_triangles


def test_rounded_macro_model_normals_are_normalised():
    rounded = [[0.7071, 0.7071, 0.0]]  # length 0.99995: a table rounded to 4 decimals
    panels = panel_set_from_panels(rounded, [0.1], [0], [0], ("panel",), ("solar_cell",), "table")
    assert np.linalg.norm(panels.outward_normals[0]) == pytest.approx(1.0, abs=1e-15)


def test_a_macro_model_normal_that_is_not_a_unit_vector_raises():
    with pytest.raises(ValueError, match="outward_normals"):
        panel_set_from_panels([[0.9, 0.0, 0.0]], [0.1], [0], [0], ("panel",), ("solar_cell",), "table")


# --- validation, whichever way a PanelSet is built ----------------------------------------------


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"areas_m2": [0.0]}, "areas_m2"),
        ({"component_ids": [1]}, "component_ids"),
        ({"component_ids": [0.0]}, "component_ids"),
        ({"material_names": ("a", "a")}, "material_names"),
        ({"component_names": ("",)}, "component_names"),
        ({"centroids_m": [[0.0, 0.0]]}, "centroids_m"),
        ({"source": ""}, "source"),
    ],
)
def test_invalid_macro_model_inputs_raise_naming_the_field(changes, field):
    arguments = {
        "outward_normals": [[1.0, 0.0, 0.0]],
        "areas_m2": [0.1],
        "component_ids": [0],
        "material_ids": [0],
        "component_names": ("bus",),
        "material_names": ("aluminium",),
        "source": "table",
    } | changes
    with pytest.raises(ValueError, match=field):
        panel_set_from_panels(**arguments)


def test_a_panel_set_whose_normals_disagree_with_its_triangles_cannot_be_created():
    properties = compute_triangle_properties(RIGHT_TRIANGLE_M)
    with pytest.raises(ValueError, match="outward_normals"):
        PanelSet(
            outward_normals=-properties.outward_normals,
            areas_m2=properties.areas_m2,
            component_ids=np.array([0]),
            material_ids=np.array([0]),
            component_names=("plate",),
            material_names=("aluminium",),
            source="inconsistent",
            centroids_m=properties.centroids_m,
            triangle_vertices_m=RIGHT_TRIANGLE_M,
        )
