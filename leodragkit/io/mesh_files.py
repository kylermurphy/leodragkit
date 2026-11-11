"""Reading triangle meshes from STL and OBJ files, converted to metres.

CAD tools export spacecraft shapes as STL (binary or ASCII) or OBJ. These readers return the triangles in
metres: a file's ``length_unit`` is required, with no default, because exports are often in millimetres and
a factor of 1000 in length is 10⁶ in area. Nothing here knows about spacecraft; ``leodragkit.aero`` turns the
triangles into components, and ``geometry_files.load_spacecraft_description`` wires mesh files into a YAML
description.

Checks at reading:

- an STL file's stored normals must agree with each triangle's corner order (an all-zero normal counts as not
  stored, as many exporters write);
- ``reverse_winding=True`` flips every triangle's corner order first, for a file wound inside out; it is
  recorded in the returned ``source``.

Read first: ``read_stl_file``, then ``read_obj_file``.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Metres per unit; exact by definition (1 in = 0.0254 m).
METRES_PER_LENGTH_UNIT = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}

# Binary STL: an 80-byte header, a 4-byte triangle count, then 50 bytes per triangle.
BINARY_STL_HEADER_BYTES = 84
BINARY_STL_RECORD = np.dtype(
    [("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute_byte_count", "<u2")]
)  # 12 + 36 + 2 = 50 bytes, little-endian


@dataclass(frozen=True)
class MeshData:
    """Triangles read from a mesh file, in metres, with the normals the file stored (STL only)."""

    triangle_vertices_m: (
        np.ndarray
    )  # (N, 3, 3), each counter-clockwise seen from outside if the file is right
    stored_normals: np.ndarray | None  # (N, 3) unit-free normals from an STL file; None if absent or all zero
    source: str  # the file, its unit, and whether the winding was reversed


def read_stl_file(path: str | Path, length_unit: str, *, reverse_winding: bool = False) -> MeshData:
    """Read a binary or ASCII STL file, returning its triangles in metres.

    Parameters
    ----------
    path
        The ``.stl`` file.
    length_unit
        The unit the file's coordinates are in: one of ``METRES_PER_LENGTH_UNIT`` ("m", "cm", "mm", "in").
    reverse_winding
        Flip every triangle's corner order (and stored normal) before checking: for a file wound inside out.

    Raises
    ------
    FileNotFoundError
        If there is no file.
    ValueError
        If the unit is unknown, the file is malformed, or stored normals disagree with the corner order (the
        message gives how many and the first).

    Example::

        mesh = read_stl_file("champ.stl", length_unit="mm")
        mesh.triangle_vertices_m.shape   # (N, 3, 3), in metres
    """
    # 1. The unit, and the raw bytes.
    file_path, metres_per_unit = _check_path_and_unit(path, length_unit)
    data = file_path.read_bytes()

    # 2. Binary or ASCII: a binary file's size is exactly 84 + 50 N, with N in bytes 80–83. (Some binary files
    #    also begin with the word "solid", so the size decides, not the first word.)
    if len(data) >= BINARY_STL_HEADER_BYTES:
        count = int(np.frombuffer(data, dtype="<u4", count=1, offset=80)[0])
        is_binary = len(data) == BINARY_STL_HEADER_BYTES + BINARY_STL_RECORD.itemsize * count
    else:
        is_binary = False
    try:
        if is_binary:
            triangles, normals = _read_binary_stl(data)
        else:
            triangles, normals = _read_ascii_stl(data.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(f"{file_path} is not a readable STL file: {error}") from error

    # 3. Metres, optional reversal, then the stored normals against the corner order.
    triangles = triangles.astype(float) * metres_per_unit
    normals = None if normals is None or not np.any(normals) else normals.astype(float)
    if reverse_winding:
        triangles = triangles[:, ::-1, :]
        normals = None if normals is None else -normals
    if normals is not None:
        _check_stored_normals(triangles, normals, file_path)
    return MeshData(triangles, normals, _describe_source(file_path, length_unit, reverse_winding))


def read_obj_file(path: str | Path, length_unit: str, *, reverse_winding: bool = False) -> MeshData:
    """Read an OBJ file's vertices (``v``) and faces (``f``), returning triangles in metres.

    Faces with more than three corners are split into a fan of triangles from their first corner. Texture and
    normal indices (``f 1/2/3 …``) are ignored; other lines (groups, materials, texture coordinates) too.

    Raises
    ------
    FileNotFoundError
        If there is no file.
    ValueError
        If the unit is unknown, the file has no faces, or a face refers to a vertex that doesn't exist.

    Example::

        mesh = read_obj_file("cubesat.obj", length_unit="m")
    """
    # 1. The unit, and the lines.
    file_path, metres_per_unit = _check_path_and_unit(path, length_unit)
    vertices, faces = [], []
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v":
            try:
                vertices.append([float(value) for value in parts[1:4]])
            except ValueError as error:
                raise ValueError(f"{file_path}, line {line_number}: a vertex needs three numbers.") from error
        elif parts[0] == "f":
            faces.append([int(corner.split("/")[0]) for corner in parts[1:]])

    # 2. Faces into triangles (your part), in metres, optionally reversed.
    if not faces:
        raise ValueError(f"{file_path} has no faces ('f' lines).")
    try:
        triangles = _triangles_from_obj_faces(np.asarray(vertices, dtype=float), faces)
    except (ValueError, IndexError) as error:
        raise ValueError(f"{file_path}: {error}") from error
    triangles = triangles * metres_per_unit
    if reverse_winding:
        triangles = triangles[:, ::-1, :]
    return MeshData(triangles, None, _describe_source(file_path, length_unit, reverse_winding))


def _read_binary_stl(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Parse a binary STL file's bytes into triangles (N, 3, 3) and stored normals (N, 3), in file units.

    After the 84-byte header, every triangle is one 50-byte record laid out as ``BINARY_STL_RECORD``: a normal
    (three little-endian 32-bit floats), three corners (nine floats), and a 2-byte attribute count.
    """
    # 1. The triangle count, from bytes 80–83 (a little-endian unsigned 32-bit integer).
    triangle_count = int(np.frombuffer(data, dtype="<u4", count=1, offset=80)[0])

    # 2. Every record at once, as a structured array laid out as BINARY_STL_RECORD.
    records = np.frombuffer(
        data, dtype=BINARY_STL_RECORD, count=triangle_count, offset=BINARY_STL_HEADER_BYTES
    )

    # 3. The corners and the stored normals, still as 32-bit floats; read_stl_file converts them.
    return records["vertices"], records["normal"]


def _triangles_from_obj_faces(vertices: np.ndarray, faces: list[list[int]]) -> np.ndarray:
    """Turn OBJ faces (lists of 1-based vertex indices) into triangles (N, 3, 3), in file units.

    OBJ counts vertices from 1, and a negative index counts back from the last vertex (−1 is the last). A face
    with corners [a, b, c, d, …] becomes the fan (a, b, c), (a, c, d), …, which keeps its corner order, so its
    winding. Raise ValueError for a face with fewer than three corners or an index that doesn't exist.
    """
    # 1. Each face: at least three corners, and every index within range before converting it to 0-based.
    #    The range check comes first: Python would accept len(vertices) + i < 0 and silently wrap round.
    n_vertices = len(vertices)
    index_triples = []
    for face in faces:
        if len(face) < 3:
            raise ValueError(f"face {face} has fewer than three corners")
        zero_based = []
        for index in face:
            if index == 0 or not -n_vertices <= index <= n_vertices:
                raise ValueError(f"face {face} refers to vertex {index}, but there are {n_vertices} vertices")
            zero_based.append(index - 1 if index > 0 else n_vertices + index)

        # 2. The fan (first, k, k + 1), which keeps the face's corner order and so its winding.
        index_triples += [
            (zero_based[0], zero_based[k], zero_based[k + 1]) for k in range(1, len(zero_based) - 1)
        ]

    # 3. All coordinates in one lookup: an (N, 3) array of index triples gives (N, 3, 3) triangles.
    return vertices[np.asarray(index_triples)]


def _read_ascii_stl(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Parse ASCII STL (``facet normal``, ``vertex`` lines) into triangles and normals, in file units."""
    normals, corners = [], []
    for line in text.splitlines():
        parts = line.split()
        if parts[:2] == ["facet", "normal"]:
            normals.append([float(value) for value in parts[2:5]])
        elif parts[:1] == ["vertex"]:
            corners.append([float(value) for value in parts[1:4]])
    if not normals or len(corners) != 3 * len(normals):
        raise ValueError(
            f"found {len(normals)} facets and {len(corners)} vertices; expected three vertices per facet"
        )
    return np.asarray(corners).reshape(-1, 3, 3), np.asarray(normals)


def _check_stored_normals(triangles_m: np.ndarray, stored_normals: np.ndarray, file_path: Path) -> None:
    """Raise if a stored normal points against its triangle's corner order (dot product below zero)."""
    winding = np.cross(triangles_m[:, 1] - triangles_m[:, 0], triangles_m[:, 2] - triangles_m[:, 0])
    disagree = np.einsum("ij,ij->i", winding, stored_normals) < 0
    if np.any(disagree):
        raise ValueError(
            f"{file_path}: {int(np.sum(disagree))} of {len(disagree)} triangles have a stored normal "
            f"pointing against their corner order (first: triangle {int(np.flatnonzero(disagree)[0])}). "
            "The file is inconsistent; if its corners are all listed clockwise, read it with "
            "reverse_winding=True."
        )


def _check_path_and_unit(path: str | Path, length_unit: str) -> tuple[Path, float]:
    """The file's path, checked to exist, and the metres per unit; raise naming what is wrong."""
    if length_unit not in METRES_PER_LENGTH_UNIT:
        raise ValueError(f"length_unit must be one of {sorted(METRES_PER_LENGTH_UNIT)}, got {length_unit!r}.")
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"No mesh file at {file_path}.")
    return file_path, METRES_PER_LENGTH_UNIT[length_unit]


def _describe_source(file_path: Path, length_unit: str, reverse_winding: bool) -> str:
    """'name.stl (mm)', with ', winding reversed' when it was."""
    return f"{file_path.name} ({length_unit}{', winding reversed' if reverse_winding else ''})"
