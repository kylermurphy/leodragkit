"""Checks that a spacecraft's triangles point outward, per component, wherever the geometry allows it.

A triangle listed clockwise has a normal pointing into the spacecraft: a ram face then contributes almost
no drag and its wake face contributes drag that isn't there, with no error. For a single triangle no test
exists, so what can be checked depends on the component:

- **Closed** components (a box, a capped cylinder): after welding corners that coincide, every edge must be
  used by two triangles running along it in opposite directions (consistent), and the signed volume must
  be positive (outward). A failure raises ``ValueError``.
- **Open, two-sided** components (a deployed panel exposed on both sides) face both ways by construction.
- **Open, one-sided** components cannot be checked strictly. When most of a component's area (at least
  ``INWARD_AREA_FRACTION_FOR_WARNING``) faces the spacecraft's area-weighted centre, its panels are reported
  with a ``GeometryOrientationWarning``, never an error.

``check_panel_set_orientation`` runs everything and is called by ``join_components``. ``summarise_geometry``
gives one row per component and displays as a table in a notebook.

Read first: ``check_component``, then ``check_panel_set_orientation``.
"""

import html
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from leodragkit.aero.geometry import PanelSet
from leodragkit.aero.repeated_warnings import warn_every_time

# Corners closer than this fraction of a component's largest dimension are the same corner.
WELD_RELATIVE_TOLERANCE = 1e-9

# A one-sided open component is flagged when at least this fraction of its area faces the spacecraft's
# centre. A plate typed the wrong way round has all of its area facing the centre; an open tube beside the
# body has about half, by its shape, and is not flagged.
INWARD_AREA_FRACTION_FOR_WARNING = 0.9


class GeometryOrientationWarning(UserWarning):
    """A one-sided panel faces the spacecraft's centre: possibly typed the wrong way round.

    Shown every time it occurs, not only the first time at a given line as Python does by default. To make
    it an error, for example in a production run:
    ``warnings.simplefilter("error", GeometryOrientationWarning)``.
    """


@dataclass(frozen=True)
class EdgeReport:
    """What the edges of a welded mesh say about it."""

    is_closed: bool  # every edge is used by exactly two triangles
    is_consistent: bool  # no directed edge (a → b) is used by more than one triangle
    problem_triangles: tuple[int, ...]  # when inconsistent: the first two triangles sharing a directed edge


@dataclass(frozen=True)
class ComponentCheck:
    """The orientation checks for one component."""

    name: str
    triangle_count: int
    area_m2: float
    is_closed: bool | None  # None when the panels have no triangles (a macro model)
    is_consistent: (
        bool | None
    )  # a two-sided plate is never consistent (front and back share edges): shown as "–"
    is_two_sided: bool | None  # every triangle has a reversed twin at the same corners
    signed_volume_m3: float | None  # only for closed components
    inward_facing_panels: tuple[
        int, ...
    ]  # panel indices flagged by the heuristic (one-sided open components)

    @property
    def status(self) -> str:
        """One word or phrase for the summary table."""
        if self.is_closed is None:
            return "not checkable (no triangles)"
        if self.is_closed and not self.is_consistent:
            return "FAIL: inconsistent winding"
        if self.is_closed and self.signed_volume_m3 <= 0:
            return "FAIL: normals point inward"
        if self.inward_facing_panels:
            return f"check: {len(self.inward_facing_panels)} panel(s) face the body"
        if self.is_closed:
            return "ok: closed, outward"
        return "ok: open, two-sided" if self.is_two_sided else "ok: open, one-sided"


@dataclass(frozen=True)
class GeometrySummary:
    """One ``ComponentCheck`` per component; prints as a text table and shows as an HTML table in Jupyter."""

    source: str
    checks: tuple[ComponentCheck, ...]

    def rows(self) -> list[dict]:
        """The table as a list of dicts, for example to build a pandas DataFrame in a notebook."""
        return [
            {
                "component": check.name,
                "triangles": check.triangle_count,
                "area (m²)": round(check.area_m2, 6),
                "closed": check.is_closed,
                "consistent": None if check.is_two_sided else check.is_consistent,
                "two-sided": check.is_two_sided,
                "signed volume (m³)": None
                if check.signed_volume_m3 is None
                else float(f"{check.signed_volume_m3:.6g}"),
                "status": check.status,
            }
            for check in self.checks
        ]

    def __str__(self) -> str:
        rows = self.rows()
        headers = list(rows[0])
        cells = [[_format_cell(row[header]) for header in headers] for row in rows]
        widths = [max(len(header), *(len(line[i]) for line in cells)) for i, header in enumerate(headers)]
        lines = [f"Geometry summary: {self.source}", "  ".join(h.ljust(w) for h, w in zip(headers, widths))]
        lines.append("  ".join("-" * width for width in widths))
        lines += ["  ".join(cell.ljust(width) for cell, width in zip(line, widths)) for line in cells]
        return "\n".join(lines)

    def _repr_html_(self) -> str:
        rows = self.rows()
        headers = "".join(f"<th>{html.escape(header)}</th>" for header in rows[0])
        body = []
        for row in rows:
            flagged = not row["status"].startswith("ok")
            style = ' style="background-color:#fde2e1"' if flagged else ""
            cells = "".join(f"<td>{html.escape(_format_cell(value))}</td>" for value in row.values())
            body.append(f"<tr{style}>{cells}</tr>")
        caption = f"<caption>Geometry summary: {html.escape(self.source)}</caption>"
        return f"<table>{caption}<thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def weld_vertices(triangle_vertices_m: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    """Merge corners that coincide into shared vertices.

    Corners are rounded to a grid of ``WELD_RELATIVE_TOLERANCE`` times the triangles' largest dimension and
    merged when they land on the same grid point. Two corners on either side of a grid line can stay
    separate, as in other welding codes; the builders here produce exactly shared corners, so this matters
    only for meshes read from files.

    Returns
    -------
    vertices_m, faces
        The distinct corners (V, 3), and each triangle as three indices into them (N, 3).
    """
    triangles = np.asarray(triangle_vertices_m, dtype=float)
    points = triangles.reshape(-1, 3)
    size_m = float(np.max(np.ptp(points, axis=0)))
    grid_m = WELD_RELATIVE_TOLERANCE * size_m if size_m > 0 else 1.0
    keys = np.round(points / grid_m).astype(np.int64)
    _, first_index, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    return points[first_index], inverse.reshape(-1, 3)


def check_edges(faces: ArrayLike) -> EdgeReport:
    """Decide from the directed edges whether a welded mesh is closed and consistently wound.

    Triangle (a, b, c) uses the directed edges a → b, b → c and c → a. The mesh is **closed** when every
    undirected edge {a, b} is used by exactly two triangles, and **consistent** when no directed edge is used
    twice: two neighbours wound the same way run along their shared edge in opposite directions.

    Parameters
    ----------
    faces
        (N, 3) integer vertex indices, from ``weld_vertices``.

    Returns
    -------
    EdgeReport
        When inconsistent, ``problem_triangles`` holds the first two triangles found sharing a directed edge.

    Example::

        _, faces = weld_vertices(build_box_triangles(1.0, 1.0, 1.0))
        check_edges(faces)   # EdgeReport(is_closed=True, is_consistent=True, problem_triangles=())
    """
    # 1. The 3N directed edges as (start, end) pairs, with the triangle each comes from.
    d_edges = np.asarray(faces)[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
    # 2. Closed: sort each pair to make it undirected; every undirected edge must occur exactly twice
    #    (np.unique with axis=0 and return_counts=True).
    sorted_edges = np.sort(d_edges, axis=1)
    _, counts = np.unique(sorted_edges, axis=0, return_counts=True)
    is_closed = bool(np.all(counts == 2))
    # 3. Consistent: no directed edge may occur twice. If one does, find the two triangles that use it.
    _, inverse, uniq_counts = np.unique(d_edges, axis=0, return_inverse=True, return_counts=True)
    is_consistent = bool(np.all(uniq_counts == 1))

    problem_triangles = ()
    if not is_consistent:
        first_duplicate = np.flatnonzero(uniq_counts > 1)[0]  # which unique edge repeats
        rows = np.flatnonzero(inverse.reshape(-1) == first_duplicate)[:2]  # the rows that hold it
        problem_triangles = tuple(int(row // 3) for row in rows)  # their triangles

    return EdgeReport(is_closed=is_closed, is_consistent=is_consistent, problem_triangles=problem_triangles)


def compute_signed_volume_m3(triangle_vertices_m: ArrayLike) -> float:
    """Signed volume enclosed by a closed triangle mesh: positive when every normal points outward.

        V = (1/6) Σ v₀ · (v₁ × v₂)

    Each term is the signed volume of the tetrahedron from the origin to one triangle; over a closed surface
    the origin's choice cancels (divergence theorem). For an open surface the number has no meaning.

    Example::

        compute_signed_volume_m3(build_box_triangles(0.1, 0.2, 0.3))   # 0.006
    """
    # 1. The three corners of every triangle (v₀, v₁, v₂), each (N, 3).
    triangle_vertices_m = np.asarray(triangle_vertices_m, dtype=float)
    v0 = triangle_vertices_m[:, 0, :]
    v1 = triangle_vertices_m[:, 1, :]
    v2 = triangle_vertices_m[:, 2, :]
    # 2. v₀ · (v₁ × v₂) per triangle (np.cross, then a row-wise dot product), summed and divided by 6.
    return float(np.sum(np.einsum("ij,ij->i", v0, np.cross(v1, v2))) / 6.0)


def check_component(
    name: str, triangle_vertices_m: ArrayLike, *, raise_on_failure: bool = True
) -> ComponentCheck:
    """Run the strict checks on one component and return its row of the summary.

    Raises
    ------
    ValueError
        With ``raise_on_failure`` (the default), if the component is closed and either inconsistently wound
        (naming two triangles on a shared edge) or of non-positive signed volume (every normal inward).
    """
    # 1. Weld, then read the edges.
    triangles = np.asarray(triangle_vertices_m, dtype=float)
    _, faces = weld_vertices(triangles)
    edges = check_edges(faces)

    # 2. Signed volume, only where it means something.
    volume_m3 = compute_signed_volume_m3(triangles) if edges.is_closed else None

    # 3. Closed components must be consistent and enclose a positive volume.
    if raise_on_failure and edges.is_closed and not edges.is_consistent:
        first, second = edges.problem_triangles
        raise ValueError(
            f"Component {name!r}: triangles {first} and {second} run along a shared edge in the same "
            "direction, so one of them is flipped: listed clockwise, not counter-clockwise, seen from "
            "outside."
        )
    if raise_on_failure and edges.is_closed and volume_m3 <= 0:
        raise ValueError(
            f"Component {name!r}: every normal points inward (signed volume {volume_m3:.6g} m³). The corners "
            "are listed clockwise seen from outside; reverse them, or for a mesh file pass "
            "reverse_winding=True."
        )

    # 4. The row; the heuristic for one-sided open components is added by the caller, which knows the body.
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return ComponentCheck(
        name=name,
        triangle_count=len(triangles),
        area_m2=float(0.5 * np.sum(np.linalg.norm(cross, axis=1))),
        is_closed=bool(edges.is_closed),
        is_consistent=bool(edges.is_consistent),
        is_two_sided=_is_two_sided(faces),
        signed_volume_m3=None if volume_m3 is None else float(volume_m3),
        inward_facing_panels=(),
    )


def summarise_geometry(panel_set: PanelSet) -> GeometrySummary:
    """One ``ComponentCheck`` per component, without raising: failures show in the status column.

    In a notebook, the returned summary displays as a table, with rows needing attention shaded.
    """
    checks = tuple(_check_every_component(panel_set, raise_on_failure=False))
    return GeometrySummary(source=panel_set.source, checks=checks)


def check_panel_set_orientation(panel_set: PanelSet) -> GeometrySummary:
    """Check every component: raise on a strict failure, warn about one-sided panels facing the body.

    Called by ``join_components``, so every spacecraft built from components is checked.

    Raises
    ------
    ValueError
        If a closed component is inconsistently wound or points inward.

    Warns
    -----
    GeometryOrientationWarning
        Naming each one-sided open component with panels facing the spacecraft's centre, and the panels.
    """
    checks = tuple(_check_every_component(panel_set, raise_on_failure=True))
    for check in checks:
        if check.inward_facing_panels:
            panels = ", ".join(str(index) for index in check.inward_facing_panels[:10])
            more = (
                ""
                if len(check.inward_facing_panels) <= 10
                else f" and {len(check.inward_facing_panels) - 10} more"
            )
            warn_every_time(
                f"{panel_set.source}: component {check.name!r} is one-sided and "
                f"{len(check.inward_facing_panels)} of its panels face the spacecraft's centre (panels "
                f"{panels}{more}). If it should face outward, turn its pose's z axis round; if it is exposed "
                "on both sides, build it two-sided.",
                GeometryOrientationWarning,
                caller_depth=2,
            )
    return GeometrySummary(source=panel_set.source, checks=checks)


def _check_every_component(panel_set: PanelSet, *, raise_on_failure: bool) -> list[ComponentCheck]:
    """Run ``check_component`` on each component and add the facing-the-body heuristic where it applies."""
    # 1. Without triangles (a macro model), nothing can be checked: one row per component saying so.
    if not panel_set.has_triangles:
        return [
            ComponentCheck(
                name,
                int(np.sum(panel_set.component_ids == index)),
                float(np.sum(panel_set.areas_m2[panel_set.component_ids == index])),
                None,
                None,
                None,
                None,
                (),
            )
            for index, name in enumerate(panel_set.component_names)
        ]

    # 2. The spacecraft's area-weighted centre, for the heuristic.
    centre_m = np.average(panel_set.centroids_m, axis=0, weights=panel_set.areas_m2)

    # 3. Each component in turn; one-sided open components get the heuristic.
    checks = []
    for index, name in enumerate(panel_set.component_names):
        panels = np.flatnonzero(panel_set.component_ids == index)
        check = check_component(
            name, panel_set.triangle_vertices_m[panels], raise_on_failure=raise_on_failure
        )
        if not check.is_closed and not check.is_two_sided:
            towards_centre = np.einsum(
                "ij,ij->i", panel_set.outward_normals[panels], panel_set.centroids_m[panels] - centre_m
            )
            facing = towards_centre < 0
            areas_m2 = panel_set.areas_m2[panels]
            if np.sum(areas_m2[facing]) >= INWARD_AREA_FRACTION_FOR_WARNING * np.sum(areas_m2):
                flagged = tuple(int(panel) for panel in panels[facing])
                check = ComponentCheck(**{**check.__dict__, "inward_facing_panels": flagged})
        checks.append(check)
    return checks


def _is_two_sided(faces: np.ndarray) -> bool:
    """True when every triangle (a, b, c) has a reversed twin (a, c, b) at the same welded corners."""

    def canonical(triangle) -> tuple[int, int, int]:
        rotation = int(np.argmin(triangle))
        return tuple(int(vertex) for vertex in np.roll(triangle, -rotation))

    present = {canonical(face) for face in faces}
    return all(canonical(face[[0, 2, 1]]) in present for face in faces)


def _format_cell(value) -> str:
    """A table cell: '–' for missing values, 'yes'/'no' for booleans."""
    if value is None:
        return "–"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
