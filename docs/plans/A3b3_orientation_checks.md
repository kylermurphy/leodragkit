# A3b3: Orientation checks

Step plan for task A3b3 in `docs/tasks.md`; part of A3 (`docs/plans/A3_geometry_overview.md`, "Checking that normals point outward"). Mode: the user writes `check_edges` and `compute_signed_volume_m3`; Claude wrote the rest of `geometry_checks.py`, the call in `join_components`, the tests, notebook section 7 and the documentation.

## Goal

Catch inward-facing triangles wherever the geometry allows it, before any physics runs (D-66, D-71), and give a per-component summary to read next to the plot.

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/aero/geometry_checks.py` | new: `weld_vertices`, `check_component`, `summarise_geometry`, `check_panel_set_orientation`, `GeometryOrientationWarning`, `EdgeReport`, `ComponentCheck`, `GeometrySummary` (written); `check_edges`, `compute_signed_volume_m3` (to write) | Claude; user |
| `leodragkit/aero/geometry_builder.py` | `join_components` step 5: check every component | Claude |
| `tests/aero/test_geometry_checks.py` | 27 tests | Claude |
| `notebooks/aero_tutorial.ipynb` | section 7: the CubeSat's summary, a broken box, a warning | Claude |
| `docs/decisions.md` | D-71 | Claude |

## How the checks work

| Component | Check | On failure |
| --- | --- | --- |
| closed (every welded edge used by two triangles) | consistent (no directed edge used twice) and signed volume > 0 | `ValueError` naming the triangles or the inward volume |
| open, two-sided (every triangle has a reversed twin) | none needed | – |
| open, one-sided | at least 90% of its area faces the spacecraft's area-weighted centre | `GeometryOrientationWarning` naming the component and panels |
| no triangles (macro model) | none possible | listed as "not checkable" |

The warning is issued so Python never hides a repeat; by default Python shows a warning only the first time it comes from a given line. It obeys warning filters, so `warnings.simplefilter("error", GeometryOrientationWarning)` turns it into an error. `summarise_geometry` returns a `GeometrySummary`: a text table when printed, an HTML table in Jupyter with rows needing attention shaded, and `rows()` for a pandas DataFrame if wanted.

## What to write

**`check_edges(faces) -> EdgeReport`**, for welded faces (N, 3):

1. The 3N directed edges a → b, b → c, c → a, each with the triangle it comes from.
2. **Closed:** sort each pair to make it undirected; every undirected edge must occur exactly twice (`np.unique(..., axis=0, return_counts=True)`).
3. **Consistent:** no directed edge may occur twice. If one does, return the first two triangles that use it as `problem_triangles`.

**`compute_signed_volume_m3(triangle_vertices_m) -> float`**: (1/6)·Σ v₀ · (v₁ × v₂), using `np.cross` and a row-wise dot product (`np.einsum("ij,ij->i", a, b)`).

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | `docs/plans/A3_geometry_overview.md`, "Checking that normals point outward" | what is checked, and why per component | 10 min |
| 2 | Wikipedia, "Polygon mesh" (https://en.wikipedia.org/wiki/Polygon_mesh): faces, vertices and edges; and "Orientability" | why neighbouring triangles must run along a shared edge in opposite directions | 15 min |
| 3 | Wikipedia, "Polyhedron", section "Volume" (https://en.wikipedia.org/wiki/Polyhedron#Volume), or any statement of the divergence theorem | why (1/6)·Σ v₀ · (v₁ × v₂) is the enclosed volume, and why its sign gives the orientation | 15 min |
| 4 | numpy: `np.unique` (`axis`, `return_counts`, `return_inverse`), `np.sort` with `axis=1`, `np.tile` | counting edges | 15 min |

## Tests

At the start: 28 failed, 178 passed in the fast suite. Every failure is a `NotImplementedError` from your two functions. That includes four earlier joining tests, because `join_components` now runs the checks. Against a scratch implementation kept out of the repository, all 206 pass and every notebook cell runs.

| Group | Tests |
| --- | --- |
| Welding | a box welds to 8 corners; nearby but distinct corners stay apart |
| Edges | a box is closed and consistent; one flipped triangle is inconsistent and named; a box missing a face is open; a flat plate is open and consistent |
| Volume | a box's signed volume is its volume; reversed, it is negative; moving the box does not change it |
| Components | box and capped cylinder pass; a flipped triangle raises ("flipped"); an inside-out box raises ("inward"); with `raise_on_failure=False` the status says so; a two-sided plate is recognised; closed, consistent and volume agree with trimesh for four shapes |
| Spacecraft | a correct spacecraft joins with no warning; a one-sided panel facing the bus warns, naming it; an open tube beside the bus does not; the warning appears every time; an inside-out component cannot be joined; the summary has one row per component, shows as an HTML table, and shades flagged rows; a macro model is "not checkable" |

## Traps

- **Directed versus undirected.** Closed counts *undirected* edges (sort each pair); consistent counts *directed* ones (don't sort).
- **Which triangles to name.** Keep each directed edge's triangle index alongside it (for example `np.tile(np.arange(N), 3)` in the same order as the edges), so a duplicated edge can be traced back.
- **Return plain types.** `is_closed` and `is_consistent` are cast to `bool` by `check_component`, but `problem_triangles` must be a tuple of Python ints, as the tests compare tuples.
- **Volume of an open surface.** `compute_signed_volume_m3` doesn't check closedness; `check_component` only calls it for closed components.

## Done when

All 27 tests in `tests/aero/test_geometry_checks.py` pass, the fast suite shows 206 passed, `ruff format --check .` and `ruff check .` pass, and notebook section 7 shows the summary, the broken box's message and the warning.
