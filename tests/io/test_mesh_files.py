"""Tests for the STL and OBJ readers (task A3d1): formats, units, stored normals and reversed winding.

The test files are written into a temporary folder from shapes with known answers (a box built by
leodragkit's own primitives); trimesh, when installed, reads the same files as an independent check.

Run: ``pytest tests/io/test_mesh_files.py``
"""

import numpy as np
import pytest

from leodragkit.aero.geometry_builder import build_box_triangles
from leodragkit.io.mesh_files import BINARY_STL_RECORD, read_obj_file, read_stl_file

BOX_M = build_box_triangles(0.1, 0.2, 0.3)


def winding_normals(triangles):
    """Unit normals from each triangle's corner order."""
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return cross / np.linalg.norm(cross, axis=1, keepdims=True)


def write_binary_stl(path, triangles, normals):
    """A binary STL file: 80-byte header, triangle count, one 50-byte record per triangle."""
    records = np.zeros(len(triangles), dtype=BINARY_STL_RECORD)
    records["normal"], records["vertices"] = normals, triangles
    path.write_bytes(
        b"leodragkit test".ljust(80, b" ") + np.uint32(len(triangles)).tobytes() + records.tobytes()
    )


def write_ascii_stl(path, triangles, normals, first_line="solid test"):
    lines = [first_line]
    for triangle, normal in zip(triangles, normals):
        lines += [f"facet normal {normal[0]} {normal[1]} {normal[2]}", "outer loop"]
        lines += [f"vertex {x} {y} {z}" for x, y, z in triangle]
        lines += ["endloop", "endfacet"]
    path.write_text("\n".join(lines + ["endsolid test"]) + "\n", encoding="utf-8")


def write_obj(path, vertices, faces):
    """An OBJ file, faces written as given (1-based or negative indices, any number of corners)."""
    lines = ["# leodragkit test", "o test"] + [f"v {x} {y} {z}" for x, y, z in vertices]
    lines += ["f " + " ".join(str(index) for index in face) for face in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- STL --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("writer", [write_binary_stl, write_ascii_stl], ids=["binary", "ascii"])
def test_an_stl_file_is_read_back_to_the_same_triangles(tmp_path, writer):
    path = tmp_path / "box.stl"
    writer(path, BOX_M, winding_normals(BOX_M))
    mesh = read_stl_file(path, length_unit="m")
    np.testing.assert_allclose(mesh.triangle_vertices_m, BOX_M, atol=1e-7)  # binary STL stores 32-bit floats
    np.testing.assert_allclose(mesh.stored_normals, winding_normals(BOX_M), atol=1e-7)
    assert mesh.source == "box.stl (m)"


def test_a_binary_stl_whose_header_starts_with_solid_is_still_read_as_binary(tmp_path):
    path = tmp_path / "box.stl"
    write_binary_stl(path, BOX_M, winding_normals(BOX_M))
    data = bytearray(path.read_bytes())
    data[:5] = b"solid"
    path.write_bytes(bytes(data))
    assert read_stl_file(path, length_unit="m").triangle_vertices_m.shape == (12, 3, 3)


@pytest.mark.parametrize(("unit", "scale"), [("mm", 1000.0), ("cm", 100.0), ("in", 1 / 0.0254)])
def test_coordinates_are_converted_to_metres(tmp_path, unit, scale):
    path = tmp_path / "box.stl"
    write_ascii_stl(path, BOX_M * scale, winding_normals(BOX_M))
    np.testing.assert_allclose(read_stl_file(path, length_unit=unit).triangle_vertices_m, BOX_M, rtol=1e-12)


def test_all_zero_stored_normals_count_as_not_stored(tmp_path):
    path = tmp_path / "box.stl"
    write_binary_stl(path, BOX_M, np.zeros((12, 3)))
    assert read_stl_file(path, length_unit="m").stored_normals is None


def test_stored_normals_against_the_corner_order_raise(tmp_path):
    path = tmp_path / "box.stl"
    normals = winding_normals(BOX_M)
    normals[3] *= -1
    write_ascii_stl(path, BOX_M, normals)
    with pytest.raises(ValueError, match="1 of 12 triangles .*first: triangle 3"):
        read_stl_file(path, length_unit="m")


def test_reverse_winding_flips_the_corners_and_the_stored_normals(tmp_path):
    inside_out = BOX_M[:, ::-1, :]
    path = tmp_path / "inside_out.stl"
    write_ascii_stl(path, inside_out, winding_normals(inside_out))
    mesh = read_stl_file(path, length_unit="m", reverse_winding=True)
    np.testing.assert_allclose(mesh.triangle_vertices_m, BOX_M, atol=1e-12)
    assert "winding reversed" in mesh.source


def test_an_stl_matches_trimesh(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    path = tmp_path / "box.stl"
    write_binary_stl(path, BOX_M, winding_normals(BOX_M))
    loaded = trimesh.load(path, force="mesh", process=False)
    np.testing.assert_allclose(
        read_stl_file(path, length_unit="m").triangle_vertices_m, loaded.triangles, atol=1e-7
    )


# --- OBJ --------------------------------------------------------------------------------------------


def test_an_obj_with_a_square_face_becomes_two_triangles_in_corner_order(tmp_path):
    path = tmp_path / "square.obj"
    write_obj(path, [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [[1, 2, 3, 4]])
    triangles = read_obj_file(path, length_unit="m").triangle_vertices_m
    np.testing.assert_allclose(
        triangles, [[[0, 0, 0], [1, 0, 0], [1, 1, 0]], [[0, 0, 0], [1, 1, 0], [0, 1, 0]]]
    )


def test_obj_texture_and_normal_indices_are_ignored_and_negative_indices_count_back(tmp_path):
    path = tmp_path / "triangle.obj"
    write_obj(path, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [["1/1/1", "2/2/1", "-1//1"]])
    np.testing.assert_allclose(
        read_obj_file(path, length_unit="m").triangle_vertices_m, [[[0, 0, 0], [1, 0, 0], [0, 1, 0]]]
    )


@pytest.mark.parametrize(
    "face",
    [[1, 2], [1, 2, 9], [0, 1, 2], [1, 2, -4]],
    ids=["two corners", "no vertex 9", "index 0", "no vertex -4"],  # -4 of 3 would otherwise wrap to the last
)
def test_a_bad_obj_face_raises_naming_the_file(tmp_path, face):
    path = tmp_path / "bad.obj"
    write_obj(path, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [face])
    with pytest.raises(ValueError, match="bad.obj"):
        read_obj_file(path, length_unit="m")


def test_an_obj_box_matches_trimesh(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    path = tmp_path / "box.obj"
    vertices = BOX_M.reshape(-1, 3)
    write_obj(path, vertices, np.arange(1, len(vertices) + 1).reshape(-1, 3).tolist())
    loaded = trimesh.load(path, force="mesh", process=False)
    np.testing.assert_allclose(
        read_obj_file(path, length_unit="m").triangle_vertices_m, loaded.triangles, atol=1e-12
    )


# --- both ---------------------------------------------------------------------------------------------


def test_an_unknown_unit_or_a_missing_file_raises(tmp_path):
    path = tmp_path / "box.stl"
    write_ascii_stl(path, BOX_M, winding_normals(BOX_M))
    with pytest.raises(ValueError, match="length_unit must be one of"):
        read_stl_file(path, length_unit="feet")
    with pytest.raises(FileNotFoundError):
        read_obj_file(tmp_path / "absent.obj", length_unit="m")
