# A3b1: Primitives and poses

**Status: done 2026-10-31.** All 167 tests pass. The user wrote `place_triangles`, `build_plate_triangles` and `build_box_triangles`; Claude wrote `build_cylinder_triangles` at the user's request. The review caught an off-by-one in the plate's cell loop and a doubled sign in the box's negative faces. The cylinder takes its segment index modulo n, so the seam reuses the first segment's exact corners: the template's 0-to-2π angles left `sin(2π)` ≈ −2.4 × 10⁻¹⁶.

Step plan for task A3b1 in `docs/tasks.md`; part of A3 (`docs/plans/A3_geometry_overview.md`). Mode: the user writes the primitive maths and the placing; Claude wrote `Pose`, `make_pose`, the resolution helper, the triangle-edge wireframe in the plot, the tests and the notebook section.

## Goal

Build the three primitives a spacecraft is assembled from (plate, box and cylinder) as outward-facing triangles in their own frames, at a chosen resolution, and place them in the body frame with a `Pose` (D-67, D-68). Joining them into one `PanelSet` is A3b2; checking orientation is A3b3.

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/aero/geometry_builder.py` | new: `Pose`, `make_pose`, `identity_pose`, `_cells_along` (written); `place_triangles`, `build_plate_triangles`, `build_box_triangles`, `build_cylinder_triangles` (to write) | Claude; user |
| `leodragkit/plots/spacecraft.py` | `show_edges`, `_add_edge_traces`, `TRIANGLE_EDGES_TRACE_NAME` (written) | Claude |
| `tests/aero/test_geometry_builder.py` | 24 tests | Claude |
| `tests/plots/test_spacecraft.py` | 2 tests for the edges | Claude |
| `notebooks/aero_tutorial.ipynb` | section 5: primitives at two resolutions, a placed panel, a cylinder | Claude |
| `docs/decisions.md` | D-67 (the A3b split, own frames, resolution), D-68 (rounded pose axes) | Claude |

## Own frames and resolution

| Primitive | Own frame | Resolution |
| --- | --- | --- |
| plate | x–y plane, centred, normal +z; `two_sided=True` appends a back face (normal −z) per facet | ⌈size / max_edge⌉ cells along each side, two triangles per cell |
| box | centred, edges along x, y, z; six plates, each placed with a pose whose z axis is the face's outward normal | the same, per face |
| cylinder | axis along z, centred; `capped=True` closes both ends with fans | n = max(8, ⌈2πR / max_edge⌉) segments, ⌈h / max_edge⌉ rows; caps not refined |

`max_edge_length_m=None` gives the coarsest mesh: one cell per face, eight cylinder segments.

## What to write

| Function | Steps (in the template) |
| --- | --- |
| `place_triangles(triangles_own_m, pose)` | rotate every corner by `pose.rotation_matrix`; add the centre |
| `build_plate_triangles(size_x_m, size_y_m, *, max_edge_length_m, two_sided)` | check sizes; cells and corner coordinates; two triangles per cell, (p00, p10, p11) and (p00, p11, p01); if two-sided, append them reversed |
| `build_box_triangles(size_x_m, size_y_m, size_z_m, *, max_edge_length_m)` | one placed plate per row of the docstring's table; concatenate in table order |
| `build_cylinder_triangles(radius_m, height_m, *, max_edge_length_m, capped)` | segments and rows; side cells (p0, p1, p2), (p0, p2, p3); if capped, top fan (centre, θₖ, θₖ₊₁) then bottom fan reversed |

The box table (in the docstring) gives each face's pose x axis, z axis and plate size. With y = z × x, every pose there is right-handed, and the plate's own x and y line up with the face's sides.

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | `docs/plans/A3_geometry_overview.md`, "Checking that normals point outward" | why the corner order matters, and what A3b3 will check | 10 min |
| 2 | `geometry_builder.py`: `Pose`, `make_pose`, the module docstring | the frames and poses you build on | 10 min |
| 3 | Rotation matrices: columns as the rotated axes; v_body = R · v_own + centre | placing | 15 min |
| 4 | numpy: `np.linspace`, `np.einsum` (or `@` with `.T`), `np.concatenate` | building grids and rotating many corners at once | 15 min |
| 5 | `notebooks/aero_tutorial.ipynb`, section 5 | what the finished primitives should look like | 5 min |

## Work order

1. `place_triangles`: two lines; the test with the identity pose goes green first.
2. `build_plate_triangles`: everything else uses it.
3. `build_box_triangles`: six calls to the two functions above.
4. `build_cylinder_triangles`.
5. Run the notebook's section 5 and look: every normal should point away from the solid, and the edges should show the resolution.

## Tests

At the start: 17 failed, 150 passed in the fast suite. Every failure is a `NotImplementedError` from a function to write; the `Pose` tests and the new edge tests pass already. Against a scratch implementation kept out of the repository, all 167 pass and every notebook cell runs.

| Group | Tests |
| --- | --- |
| Pose | y = z × x and det R = 1; rounded axes made exact; nearly-but-not-unit or non-perpendicular axes raise; a `Pose` built directly must be exact |
| Placing | the identity changes nothing; a placed plate's normal becomes the pose's z axis and its centre the pose's centre; its own x lies along the pose's x |
| Plate | coarse: two triangles, normal +z, area, extent, centred; finer: cell count and cell sides ≤ the maximum edge; two-sided: front then back, opposite normals; non-positive sizes raise |
| Box | area 2(ab + bc + ca); every normal points away from the centre; extent; faces in table order; closed, consistently wound, volume abc (trimesh), coarse and fine |
| Cylinder | eight segments when coarse; faceted side and cap areas; side normals radial, caps ±z; segment and row counts and edge lengths when finer; uncapped is open, capped is closed with the prism's volume (trimesh) |

## Traps

- **Rotating the right axis.** `triangles` is (N, 3, 3): the last axis holds coordinates. `np.einsum("ij,nkj->nki", R, triangles)` rotates every corner; `triangles @ R.T` does the same.
- **Cell corners in order.** With p00, p10, p11, p01 counter-clockwise seen from +z, the triangles are (p00, p10, p11) and (p00, p11, p01). Swapping two corners flips the normal, and the box test will catch it.
- **Back faces after front faces.** A two-sided plate appends all reversed triangles after all front ones; the tests rely on that order.
- **Closing the circle.** The last side segment joins θₙ₋₁ to θₙ = 2π, the same point as θ₀. Use angles 2πk/n for k = 0 … n, so the seam is closed, and trimesh's watertight check passes once corners are welded.
- **Cap direction.** The top fan (centre, θₖ, θₖ₊₁) runs counter-clockwise seen from +z; the bottom fan needs the opposite order to face −z.

## Done when

All 24 tests in `tests/aero/test_geometry_builder.py` pass, the fast suite shows 167 passed, `ruff format --check .` and `ruff check .` pass, and section 5 of the notebook shows every normal pointing outward. Then send `geometry_builder.py` for review.
