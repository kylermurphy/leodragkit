"""Build spacecraft geometry from primitives: plates, boxes and cylinders, placed at poses.

Each primitive is built centred on its own origin as an (N, 3, 3) array of outward triangles, then placed
in the body frame by a ``Pose``. Joining placed components into one ``PanelSet`` comes in the next step.

Own frames: a plate lies in the x–y plane with its normal along +z; a box has its edges along x, y and z;
a cylinder has its axis along z. Every triangle is counter-clockwise seen from outside, so its normal
points outward (the geometry conventions in ``.claude/rules/aero.md``).

Resolution: ``max_edge_length_m`` splits each rectangle into cells no longer than that on each side, two
triangles per cell; ``None`` means the coarsest mesh, one cell per face. Finer meshes matter for shadowing,
where each triangle is wholly lit or wholly shadowed.

Read first: ``Pose`` and ``make_pose``, then ``place_triangles``, then the primitives.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

# Hand-typed axes are rounded (for example [0, 0.7071, 0.7071]); within this tolerance they are made
# exactly unit length and perpendicular, beyond it they raise.
POSE_AXIS_TOLERANCE = 1e-3

# Inside a Pose the axes are orthonormal to rounding error.
ORTHONORMAL_TOLERANCE = 1e-9

# A cylinder's side is faceted into at least this many segments, however coarse the resolution.
MINIMUM_CYLINDER_SEGMENTS = 8


@dataclass(frozen=True)
class Pose:
    """Where a component sits in the body frame: its centre and its own x and z axes.

    The y axis is z × x, so the axes are right-handed by construction. Build one with ``make_pose``,
    which accepts rounded axes; a ``Pose`` itself insists on exact unit, perpendicular axes.
    """

    centre_m: np.ndarray  # (3,) in the body frame
    x_axis: np.ndarray  # (3,) unit vector, the component's own x in the body frame
    z_axis: np.ndarray  # (3,) unit vector, perpendicular to x_axis

    def __post_init__(self) -> None:
        for name in ("centre_m", "x_axis", "z_axis"):
            value = getattr(self, name)
            if np.shape(value) != (3,) or not np.all(np.isfinite(value)):
                raise ValueError(f"Pose.{name} must be three finite numbers, got {value!r}.")
        for name in ("x_axis", "z_axis"):
            if abs(np.linalg.norm(getattr(self, name)) - 1.0) > ORTHONORMAL_TOLERANCE:
                raise ValueError(f"Pose.{name} must be a unit vector; use make_pose for rounded axes.")
        if abs(np.dot(self.x_axis, self.z_axis)) > ORTHONORMAL_TOLERANCE:
            raise ValueError(
                "Pose.x_axis and Pose.z_axis must be perpendicular; use make_pose for rounded axes."
            )

    @property
    def y_axis(self) -> np.ndarray:
        """The component's own y axis in the body frame, z × x."""
        return np.cross(self.z_axis, self.x_axis)

    @property
    def rotation_matrix(self) -> np.ndarray:
        """(3, 3) matrix whose columns are the x, y and z axes: v_body = R · v_own + centre."""
        return np.column_stack([self.x_axis, self.y_axis, self.z_axis])


def make_pose(centre_m: ArrayLike, x_axis: ArrayLike, z_axis: ArrayLike) -> Pose:
    """Return a ``Pose``, accepting axes rounded to within ``POSE_AXIS_TOLERANCE``.

    Within the tolerance, the axes are made exact: x is normalised, then z loses its component along x and
    is normalised. Beyond it, a ``ValueError`` names what is wrong.

    Example::

        panel_pose = make_pose(centre_m=[0, 0.2, 0], x_axis=[1, 0, 0], z_axis=[0, 0.7071, 0.7071])
    """
    # 1. Three finite numbers each.
    centre, x, z = (np.asarray(value, dtype=float) for value in (centre_m, x_axis, z_axis))
    for name, value in (("centre_m", centre), ("x_axis", x), ("z_axis", z)):
        if value.shape != (3,) or not np.all(np.isfinite(value)):
            raise ValueError(f"{name} must be three finite numbers, got {value!r}.")

    # 2. Unit length and perpendicular, within the rounding allowance.
    for name, value in (("x_axis", x), ("z_axis", z)):
        if abs(np.linalg.norm(value) - 1.0) > POSE_AXIS_TOLERANCE:
            raise ValueError(
                f"{name} must have length 1 within {POSE_AXIS_TOLERANCE}, got {np.linalg.norm(value):.6g}."
            )
    if abs(np.dot(x, z)) > POSE_AXIS_TOLERANCE:
        raise ValueError(
            f"x_axis and z_axis must be perpendicular within {POSE_AXIS_TOLERANCE}; x·z = {np.dot(x, z):.6g}."
        )

    # 3. Make them exact: normalise x, remove x's component from z, normalise z.
    x = x / np.linalg.norm(x)
    z = z - np.dot(z, x) * x
    return Pose(centre_m=centre, x_axis=x, z_axis=z / np.linalg.norm(z))


def identity_pose() -> Pose:
    """The pose that leaves a primitive where it was built: centred on the body origin, axes aligned."""
    return Pose(centre_m=np.zeros(3), x_axis=np.array([1.0, 0.0, 0.0]), z_axis=np.array([0.0, 0.0, 1.0]))


def place_triangles(triangles_own_m: ArrayLike, pose: Pose) -> np.ndarray:
    """Move triangles from a primitive's own frame into the body frame: v_body = R · v_own + centre.

    Rotating every corner by the same proper rotation keeps the corner order, so outward stays outward.

    Parameters
    ----------
    triangles_own_m
        (N, 3, 3) triangles in the primitive's own frame, metres.
    pose
        Where the primitive sits.

    Returns
    -------
    np.ndarray
        (N, 3, 3) triangles in the body frame, metres.

    Example::

        body_triangles_m = place_triangles(build_plate_triangles(0.3, 0.1), panel_pose)
    """
    # 1. Rotate every corner with pose.rotation_matrix (np.einsum or the @ operator on the last axis).
    r_triangles = triangles_own_m @ pose.rotation_matrix.T

    # 2. Add the centre.
    return r_triangles + pose.centre_m


def build_plate_triangles(
    size_x_m: float, size_y_m: float, *, max_edge_length_m: float | None = None, two_sided: bool = False
) -> np.ndarray:
    """Triangles of a flat rectangle in the x–y plane, centred on the origin, normal +z.

    The rectangle is split into ``_cells_along(size_x_m, …)`` × ``_cells_along(size_y_m, …)`` cells, each
    two triangles counter-clockwise seen from +z: with cell corners p00, p10, p11, p01 (counter-clockwise),
    the triangles are (p00, p10, p11) and (p00, p11, p01).

    With ``two_sided=True``, every cell also gets the same two triangles in reverse order, normal −z, after
    all the front triangles: a thin panel exposed on both sides.

    Returns
    -------
    np.ndarray
        (2·nx·ny, 3, 3) triangles, or twice that when two-sided.

    Raises
    ------
    ValueError
        If a size or the maximum edge length is not positive.

    Example::

        solar_panel_m = build_plate_triangles(0.3, 0.1, max_edge_length_m=0.05, two_sided=True)
    """
    # 1. Check the sizes are positive (the maximum edge length is checked by _cells_along).
    if size_x_m <= 0 or size_y_m <= 0:
        raise ValueError(f"size_x_m and size_y_m must be positive, got {size_x_m!r} and {size_y_m!r}.")
    # 2. Number of cells along x and y, and the corner coordinates (np.linspace from −size/2 to +size/2).
    xn_cell = _cells_along(size_x_m, max_edge_length_m=max_edge_length_m)
    yn_cell = _cells_along(size_y_m, max_edge_length_m=max_edge_length_m)

    # 3. For every cell, its two front triangles.
    n_triangles = 2 * xn_cell * yn_cell
    cell_triangles = np.ndarray((n_triangles, 3, 3))
    i = 0
    x_spc = size_x_m / xn_cell
    y_spc = size_y_m / yn_cell
    for x in np.linspace(-size_x_m / 2, size_x_m / 2, xn_cell + 1):
            for y in np.linspace(-size_y_m / 2, size_y_m / 2, yn_cell + 1):
                cell_triangles[i] = [[x, y, 0], [x + x_spc, y, 0], [x + x_spc, y + y_spc, 0]]
                cell_triangles[i + 1] = [[x, y, 0], [x + x_spc, y + y_spc, 0], [x, y + y_spc, 0]]
                i += 2

    # 4. If two-sided, append every front triangle with its corners reversed.
    return cell_triangles if not two_sided else np.concatenate([cell_triangles, cell_triangles[:, ::-1, :]], axis=0)


def build_box_triangles(
    size_x_m: float, size_y_m: float, size_z_m: float, *, max_edge_length_m: float | None = None
) -> np.ndarray:
    """Triangles of a closed box centred on the origin, edges along x, y and z, every normal outward.

    Built from six plates, each placed with a pose whose z axis is the face's outward normal. The plate's
    own x and y must match the face's sizes; with y = z × x, these poses work:

    ====  ===============  ===============  ==============
    Face  pose x axis      pose z axis      plate size
    ====  ===============  ===============  ==============
    +x    (0, 1, 0)        (1, 0, 0)        (size_y, size_z)
    −x    (0, −1, 0)       (−1, 0, 0)       (size_y, size_z)
    +y    (0, 0, 1)        (0, 1, 0)        (size_z, size_x)
    −y    (0, 0, −1)       (0, −1, 0)       (size_z, size_x)
    +z    (1, 0, 0)        (0, 0, 1)        (size_x, size_y)
    −z    (−1, 0, 0)       (0, 0, −1)       (size_x, size_y)
    ====  ===============  ===============  ==============

    Each face's centre is half the box's size along its normal. Faces appear in the order of the table.

    Example::

        bus_m = build_box_triangles(0.1, 0.1, 0.34, max_edge_length_m=0.05)
    """
    # 1. For each row of the table: a one-sided plate of the face's size, placed at its pose.
    # 2. Concatenate the six faces in table order.
    raise NotImplementedError("build_box_triangles: six placed plates, one per row of the table.")


def build_cylinder_triangles(
    radius_m: float, height_m: float, *, max_edge_length_m: float | None = None, capped: bool = True
) -> np.ndarray:
    """Triangles of a cylinder centred on the origin, axis along z, every normal outward.

    The side is faceted into n segments, n = max(MINIMUM_CYLINDER_SEGMENTS, ⌈2πR / max_edge_length_m⌉)
    (just MINIMUM_CYLINDER_SEGMENTS when the maximum edge length is None), and into
    ``_cells_along(height_m, …)`` rows. With angles θ_k = 2πk/n and heights z_l, each side cell has corners
    p0 = (θ_k, z_l), p1 = (θ_k+1, z_l), p2 = (θ_k+1, z_l+1), p3 = (θ_k, z_l+1), giving triangles (p0, p1, p2)
    and (p0, p2, p3); their normals point radially outward.

    With ``capped=True`` the two ends are closed by fans from their centres: the top (z = +h/2) with
    triangles (centre, θ_k, θ_k+1), normal +z, and the bottom with the same corners reversed, normal −z.
    The caps are not refined by ``max_edge_length_m``: their triangles reach from the centre to the rim.

    Side triangles come first, then the top cap, then the bottom cap.

    Example::

        boom_m = build_cylinder_triangles(0.01, 0.5, max_edge_length_m=0.05, capped=False)
    """
    # 1. Check radius and height are positive; number of segments and rows.
    # 2. Angles and heights; the corner coordinates (R cos θ, R sin θ, z).
    # 3. The side cells, two triangles each.
    # 4. If capped, the top and bottom fans.
    raise NotImplementedError("build_cylinder_triangles: side cells, then optional caps.")


def _cells_along(length_m: float, max_edge_length_m: float | None) -> int:
    """Number of cells along a length so none is longer than ``max_edge_length_m``; 1 when it is None."""
    if max_edge_length_m is None:
        return 1
    if not np.isfinite(max_edge_length_m) or max_edge_length_m <= 0:
        raise ValueError(f"max_edge_length_m must be positive, got {max_edge_length_m!r}.")
    return max(1, int(np.ceil(length_m / max_edge_length_m - 1e-12)))
