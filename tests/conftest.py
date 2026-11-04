"""Shared test fixtures: small spacecraft geometries built by hand, used by the aero and plots tests."""

import numpy as np
import pytest

from leodragkit.aero.geometry import PanelSet, panel_set_from_triangles


def build_unit_cube_triangles_m() -> np.ndarray:
    """The 12 triangles of a unit cube centred on the origin, each counter-clockwise seen from outside.

    Faces in order −x, +x, −y, +y, −z, +z, two triangles each.
    """
    corners = np.array(
        [[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
    )  # index = 4·(x > 0) + 2·(y > 0) + (z > 0)
    faces = [  # each face as four corners, counter-clockwise seen from outside
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


@pytest.fixture
def unit_cube_triangles_m() -> np.ndarray:
    """The 12 triangles of a unit cube centred on the origin (see ``build_unit_cube_triangles_m``)."""
    return build_unit_cube_triangles_m()


@pytest.fixture
def unit_cube_panel_set() -> PanelSet:
    """A unit cube with two components and two materials, for tests that need variety.

    The four side faces (±x, ±y) are the component "body" and the two z faces are "end_caps"; the ±x
    and ±z faces are "aluminium" and the ±y faces are "solar_cell".
    """
    component_ids = np.array([0] * 8 + [1] * 4)
    material_ids = np.array([0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0])
    return panel_set_from_triangles(
        build_unit_cube_triangles_m(),
        component_ids,
        material_ids,
        ("body", "end_caps"),
        ("aluminium", "solar_cell"),
        source="unit cube (test fixture)",
    )
