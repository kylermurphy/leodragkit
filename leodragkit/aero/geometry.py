"""The one geometry the aero solver sees: a set of flat panels, ``PanelSet``.

Every way of describing a spacecraft (primitives, YAML descriptions, macro-model tables, STL or OBJ
meshes) ends here. A panel has an outward unit normal, an area, a component and a material. When it
was built from triangles it also has its corners and centroid; a macro model may have neither, and then
supports forces but not shadowing or moments.

Conventions: body frame, metres. A triangle's outward normal follows its corner order, counter-clockwise
seen from outside: n̂ = (v₁ − v₀) × (v₂ − v₀) / |(v₁ − v₀) × (v₂ − v₀)|.

Read first: ``PanelSet``, then ``compute_triangle_properties``, then the two constructors.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

# A triangle whose area is this small relative to its longest edge squared has (nearly) collinear
# corners: its normal is meaningless, so it is rejected rather than dropped.
DEGENERATE_RELATIVE_AREA = 1e-12

# Published macro-model tables round their normals (often to 4 decimals), so |n̂| can miss 1 by ~1e-4.
# Normals within this tolerance are normalised; anything further off is an error in the table.
MACRO_MODEL_NORMAL_LENGTH_TOLERANCE = 1e-3

# Inside a PanelSet, normals are unit vectors to rounding error, and values derived from triangles must
# match the stored ones to this relative tolerance.
UNIT_NORMAL_TOLERANCE = 1e-9


@dataclass(frozen=True)
class TriangleProperties:
    """Outward normals, areas and centroids of N triangles, as derived from their corners."""

    outward_normals: np.ndarray  # (N, 3) unit vectors
    areas_m2: np.ndarray  # (N,)
    centroids_m: np.ndarray  # (N, 3)


@dataclass(frozen=True)
class PanelSet:
    """N flat panels in the body frame: the canonical geometry for the aero solver.

    Build one with ``panel_set_from_triangles`` or ``panel_set_from_panels``; both validate their
    inputs, and every ``PanelSet`` is checked again when it is created, so an invalid one cannot exist.
    """

    outward_normals: np.ndarray  # (N, 3) unit vectors
    areas_m2: np.ndarray  # (N,) > 0
    component_ids: np.ndarray  # (N,) integers indexing component_names
    material_ids: np.ndarray  # (N,) integers indexing material_names
    component_names: tuple[str, ...]
    material_names: tuple[str, ...]
    source: str  # the file or description the panels came from, for provenance
    centroids_m: np.ndarray | None = None  # (N, 3); None for macro models without positions
    triangle_vertices_m: np.ndarray | None = None  # (N, 3, 3); None unless built from triangles

    def __post_init__(self) -> None:
        _check_panel_set(self)

    @property
    def panel_count(self) -> int:
        """Number of panels, N."""
        return len(self.areas_m2)

    @property
    def has_positions(self) -> bool:
        """True when panel centroids are known (needed for moments)."""
        return self.centroids_m is not None

    @property
    def has_triangles(self) -> bool:
        """True when triangle corners are known (needed for shadowing and 3-D plots)."""
        return self.triangle_vertices_m is not None


def compute_triangle_properties(triangle_vertices_m: ArrayLike) -> TriangleProperties:
    """Return the outward normal, area and centroid of each triangle.

    For a triangle with corners v₀, v₁, v₂, listed counter-clockwise seen from outside:

        cross = (v₁ − v₀) × (v₂ − v₀)
        area = |cross| / 2
        outward normal = cross / |cross|
        centroid = (v₀ + v₁ + v₂) / 3

    Parameters
    ----------
    triangle_vertices_m
        (N, 3, 3) array: N triangles, 3 corners each, 3 coordinates per corner, in metres.

    Returns
    -------
    TriangleProperties
        Normals (N, 3), areas in m² (N,) and centroids in m (N, 3).

    Raises
    ------
    ValueError
        If the array is not (N, 3, 3) or not finite, or if a triangle is degenerate: its area is at most
        ``DEGENERATE_RELATIVE_AREA`` times its longest edge squared. The message gives the triangle's index.

    Example::

        properties = compute_triangle_properties([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]])
        properties.outward_normals   # [[0, 0, 1]]
    """
    # 1. Check the array with _as_finite_array(..., trailing_shape=(3, 3)).
    vertices = _as_finite_array("triangle_vertices_m", triangle_vertices_m, trailing_shape=(3, 3))
    # 2. Edge vectors v₁ − v₀ and v₂ − v₀, and their cross product (np.cross works on the last axis).
    edge_10 = vertices[:, 1, :] - vertices[:, 0, :]
    edge_20 = vertices[:, 2, :] - vertices[:, 0, :]
    edge_21 = vertices[:, 2, :] - vertices[:, 1, :]
    # 3. Areas, and the degenerate check: compare each area with its longest edge squared
    #    (all three edges, including v₂ − v₁); raise naming the first bad triangle's index.
    cross = np.cross(edge_10, edge_20)
    cross_length = np.linalg.norm(cross, axis=1)
    areas_m2 = 0.5 * cross_length

    # square of edge lengths
    e10_l2 = np.sum(edge_10**2, axis=1)
    e20_l2 = np.sum(edge_20**2, axis=1)
    e21_l2 = np.sum(edge_21**2, axis=1)
    longest_l2 = np.maximum(np.maximum(e10_l2, e20_l2), e21_l2)

    is_degenerate = areas_m2 <= DEGENERATE_RELATIVE_AREA * longest_l2
    if np.any(is_degenerate):
        index = int(np.flatnonzero(is_degenerate)[0])
        raise ValueError(
            f"triangle_vertices_m: triangle {index} is degenerate; area {areas_m2[index]:.6g} "
            f"≤ {DEGENERATE_RELATIVE_AREA} × longest edge² {longest_l2[index]:.6g}."
        )
    # 4. Outward normals: the cross products divided by their lengths (keep the last axis, keepdims=True).
    outward_normals = cross / cross_length[:, np.newaxis]
    # 5. Centroids: the mean of the three corners.
    centroids_m = np.mean(vertices, axis=1)

    return TriangleProperties(outward_normals=outward_normals, areas_m2=areas_m2, centroids_m=centroids_m)


def panel_set_from_triangles(
    triangle_vertices_m: ArrayLike,
    component_ids: ArrayLike,
    material_ids: ArrayLike,
    component_names: tuple[str, ...],
    material_names: tuple[str, ...],
    source: str,
) -> PanelSet:
    """Build a ``PanelSet`` from triangles, deriving normals, areas and centroids from the corners.

    Example::

        panels = panel_set_from_triangles(
            [[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], [0], [0], ("plate",), ("aluminium",), source="example"
        )
    """
    # 1. Derive normals, areas and centroids from the corners.
    vertices = _as_finite_array("triangle_vertices_m", triangle_vertices_m, trailing_shape=(3, 3))
    properties = compute_triangle_properties(vertices)

    # 2. Assemble; PanelSet checks ids, names and consistency when it is created.
    return PanelSet(
        outward_normals=properties.outward_normals,
        areas_m2=properties.areas_m2,
        component_ids=_as_id_array("component_ids", component_ids),
        material_ids=_as_id_array("material_ids", material_ids),
        component_names=tuple(component_names),
        material_names=tuple(material_names),
        source=source,
        centroids_m=properties.centroids_m,
        triangle_vertices_m=vertices,
    )


def panel_set_from_panels(
    outward_normals: ArrayLike,
    areas_m2: ArrayLike,
    component_ids: ArrayLike,
    material_ids: ArrayLike,
    component_names: tuple[str, ...],
    material_names: tuple[str, ...],
    source: str,
    centroids_m: ArrayLike | None = None,
) -> PanelSet:
    """Build a ``PanelSet`` from bare panels, as in a macro-model table: normals, areas, optional centroids.

    Normals whose length is within ``MACRO_MODEL_NORMAL_LENGTH_TOLERANCE`` of 1 (rounded tables) are
    normalised; anything further off raises. Without centroids the set supports forces but not moments.

    Example::

        panels = panel_set_from_panels([[1, 0, 0]], [0.03], [0], [0], ("bus",), ("aluminium",), "table")
    """
    # 1. Check the normals and normalise those within the rounding allowance.
    normals = _as_finite_array("outward_normals", outward_normals, trailing_shape=(3,))
    lengths = np.linalg.norm(normals, axis=1)
    if np.any(np.abs(lengths - 1.0) > MACRO_MODEL_NORMAL_LENGTH_TOLERANCE):
        index = int(np.argmax(np.abs(lengths - 1.0)))
        raise ValueError(
            f"outward_normals: panel {index} has length {lengths[index]:.6g}; normals must have length 1 "
            f"within {MACRO_MODEL_NORMAL_LENGTH_TOLERANCE} ({source})."
        )
    normals = normals / lengths[:, np.newaxis]

    # 2. Assemble; PanelSet checks the rest when it is created.
    return PanelSet(
        outward_normals=normals,
        areas_m2=_as_finite_array("areas_m2", areas_m2, trailing_shape=()),
        component_ids=_as_id_array("component_ids", component_ids),
        material_ids=_as_id_array("material_ids", material_ids),
        component_names=tuple(component_names),
        material_names=tuple(material_names),
        source=source,
        centroids_m=None
        if centroids_m is None
        else _as_finite_array("centroids_m", centroids_m, trailing_shape=(3,)),
    )


def _check_panel_set(panels: PanelSet) -> None:
    """Raise ValueError, naming the field, if a PanelSet's arrays, ids or names are inconsistent."""
    # 1. Shapes: everything per panel has N rows.
    count = len(panels.areas_m2)
    expected_shapes = {
        "outward_normals": (panels.outward_normals, (count, 3)),
        "areas_m2": (panels.areas_m2, (count,)),
        "component_ids": (panels.component_ids, (count,)),
        "material_ids": (panels.material_ids, (count,)),
    }
    if panels.centroids_m is not None:
        expected_shapes["centroids_m"] = (panels.centroids_m, (count, 3))
    if panels.triangle_vertices_m is not None:
        expected_shapes["triangle_vertices_m"] = (panels.triangle_vertices_m, (count, 3, 3))
    for name, (values, shape) in expected_shapes.items():
        if np.shape(values) != shape:
            raise ValueError(f"{name} has shape {np.shape(values)}, expected {shape} ({panels.source}).")
    if count == 0:
        raise ValueError(f"A PanelSet needs at least one panel ({panels.source}).")

    # 2. Values: finite, positive areas, unit normals.
    for name in ("outward_normals", "areas_m2", "centroids_m", "triangle_vertices_m"):
        values = getattr(panels, name)
        if values is not None and not np.all(np.isfinite(values)):
            raise ValueError(f"{name} must be finite ({panels.source}).")
    if np.any(panels.areas_m2 <= 0):
        raise ValueError(
            f"areas_m2 must be > 0; panel {int(np.argmin(panels.areas_m2))} is not ({panels.source})."
        )
    if np.any(np.abs(np.linalg.norm(panels.outward_normals, axis=1) - 1.0) > UNIT_NORMAL_TOLERANCE):
        raise ValueError(f"outward_normals must be unit vectors ({panels.source}).")

    # 3. Ids and names: integer ids within range, unique non-empty names.
    for ids_name, names_name in (("component_ids", "component_names"), ("material_ids", "material_names")):
        ids, names = getattr(panels, ids_name), getattr(panels, names_name)
        if not all(isinstance(name, str) and name for name in names) or len(set(names)) != len(names):
            raise ValueError(f"{names_name} must be unique, non-empty strings; got {names!r}.")
        if not np.issubdtype(ids.dtype, np.integer) or np.any(ids < 0) or np.any(ids >= len(names)):
            raise ValueError(f"{ids_name} must be integers from 0 to {len(names) - 1} ({panels.source}).")
    if not isinstance(panels.source, str) or not panels.source:
        raise ValueError("source must be a non-empty string naming where the panels came from.")

    # 4. Triangles, when present, must agree with the normals, areas and centroids stored beside them.
    if panels.triangle_vertices_m is not None:
        if panels.centroids_m is None:
            raise ValueError(f"centroids_m must be given when triangle_vertices_m is ({panels.source}).")
        derived = compute_triangle_properties(panels.triangle_vertices_m)
        for name in ("outward_normals", "areas_m2", "centroids_m"):
            if not np.allclose(
                getattr(panels, name), getattr(derived, name), rtol=UNIT_NORMAL_TOLERANCE, atol=0
            ):
                raise ValueError(f"{name} does not match triangle_vertices_m ({panels.source}).")


def _as_finite_array(name: str, values: ArrayLike, trailing_shape: tuple[int, ...]) -> np.ndarray:
    """Return ``values`` as a float64 array of shape (N, *trailing_shape).

    Raises ValueError naming ``name`` if the shape is wrong, N is 0 or a value is not finite.
    """
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 + len(trailing_shape) or array.shape[1:] != trailing_shape or len(array) == 0:
        expected = "(N" + "".join(f", {size}" for size in trailing_shape) + ")"
        raise ValueError(f"{name} must have shape {expected} with N ≥ 1, got {array.shape}.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite.")
    return array


def _as_id_array(name: str, values: ArrayLike) -> np.ndarray:
    """Return ``values`` as an integer array; raise ValueError naming ``name`` if they are not integers."""
    array = np.asarray(values)
    if not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"{name} must be integers, got dtype {array.dtype}.")
    return array
