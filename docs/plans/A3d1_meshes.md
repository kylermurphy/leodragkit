# A3d1: Spacecraft from mesh files (STL, OBJ)

Step plan for task A3d1 in `docs/tasks.md`; part of A3 (`docs/plans/A3_geometry_overview.md`). Mode: the user writes the binary STL reader and the OBJ face parsing; Claude wrote the rest of `io/mesh_files.py`, the description wiring, the direct path, the tests, notebook section 10, the guide section and the documentation.

## Goal

Read spacecraft shapes exported from CAD tools, STL (binary and ASCII) and OBJ, as triangles in metres. Use them either on their own (`build_spacecraft_from_triangles`) or as `shape: mesh` components in a YAML description, alongside primitives (D-77).

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/io/mesh_files.py` | new: `read_stl_file`, `read_obj_file`, `MeshData`, the ASCII reader, the checks (written); `_read_binary_stl`, `_triangles_from_obj_faces` (to write) | Claude; user |
| `leodragkit/io/geometry_files.py` | `load_spacecraft_description`: a description plus the mesh files it names | Claude |
| `leodragkit/aero/spacecraft.py` | `shape: mesh`; `build_spacecraft_from_triangles`; the mesh branch in `_build_component` | Claude |
| `tests/io/test_mesh_files.py` | new: 17 tests | Claude |
| `tests/io/test_geometry_files.py`, `tests/aero/test_spacecraft_description.py` | mesh loading and building | Claude |
| `notebooks/aero_tutorial.ipynb` | section 10: an STL written in millimetres, read directly and in a description | Claude |
| `docs/guides/describing_a_spacecraft.md` | section 5a, "Shapes from a mesh file" | Claude |

## What to write

**`_read_binary_stl(data) -> (triangles, normals)`**:

1. The triangle count, from bytes 80–83: `np.frombuffer(data, dtype="<u4", count=1, offset=80)[0]`.
2. All records at once: `np.frombuffer(data, dtype=BINARY_STL_RECORD, count=…, offset=BINARY_STL_HEADER_BYTES)`.
3. Return the `"vertices"` field (N, 3, 3) and the `"normal"` field (N, 3).

**`_triangles_from_obj_faces(vertices, faces) -> triangles`**:

1. For each face, check it has at least three corners.
2. Convert each index to 0-based: positive i becomes i − 1, and negative i becomes len(vertices) + i. Raise a `ValueError` for 0 or anything out of range.
3. Split the face into a fan: (first, k, k + 1) for each k from the second corner to the second-to-last.
4. Look up the coordinates all at once: `vertices[np.asarray(index_triples)]`.

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | Wikipedia, "STL (file format)" (https://en.wikipedia.org/wiki/STL_(file_format)): "Binary STL" | the 80-byte header, the count, the 50-byte record | 10 min |
| 2 | Wikipedia, "Wavefront .obj file" (https://en.wikipedia.org/wiki/Wavefront_.obj_file): "Geometric vertex", "Face elements" | 1-based and negative indices; `v/vt/vn` | 10 min |
| 3 | numpy: structured data types (https://numpy.org/doc/stable/user/basics.rec.html) and `np.frombuffer` | reading binary records without a loop | 15 min |
| 4 | `docs/guides/describing_a_spacecraft.md`, section 5a | how users will use what you write | 5 min |

## Tests

At the start: 11 failed, 254 passed in the fast suite. Every failure is a `NotImplementedError` from your two functions (including one description test that reads an OBJ file). Against a scratch implementation kept out of the repository, all 265 pass and every notebook cell runs.

| Group | Tests |
| --- | --- |
| STL | binary and ASCII read back to the same triangles and normals; a binary file whose header starts with "solid" is still binary; mm, cm and in convert to metres; all-zero normals count as not stored; one stored normal against its corners raises, naming it; `reverse_winding` flips corners and normals; trimesh reads the same triangles |
| OBJ | a square face becomes two triangles in corner order; texture and normal indices are ignored and negative indices count back; two corners, a missing vertex and index 0 each raise naming the file; trimesh reads the same triangles |
| Both | an unknown unit or a missing file raises |
| Descriptions | mesh files are read relative to the description, in metres; another file type raises naming the component; a loaded mesh is placed at its pose; an unloaded mesh says how to load it; a spacecraft straight from triangles; an inside-out mesh cannot be built |

## Traps

- **Endianness.** STL is little-endian; `BINARY_STL_RECORD` already says so (`<f4`, `<u2`). A plain `float32` dtype would also work on most machines, but not all.
- **Read-only arrays.** `np.frombuffer` returns a view of the bytes, which cannot be written to. That's fine here, because `read_stl_file` converts to float with `astype`, which makes a copy.
- **OBJ counts from 1.** Index 0 is invalid, and −1 is the last vertex.
- **The fan keeps the winding.** (a, b, c), (a, c, d) preserves the face's corner order; (a, c, b) would flip it.

## Done when

All A3d1 tests pass, the fast suite shows 265 passed, `ruff format --check .` and `ruff check .` pass, and notebook section 10 shows the cylindrical bus read from millimetres, and the bus with two panels, every summary row "ok".
