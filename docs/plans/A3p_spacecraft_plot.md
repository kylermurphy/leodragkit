# A3p: Interactive 3-D plot of a `PanelSet`

Step plan for task A3p in `docs/tasks.md`; part of A3 (`docs/plans/A3_geometry_overview.md`). Mode: the user writes the plotting code; Claude wrote the template, the helpers that are not plotting (importing plotly, sizing), the tests, the shared test fixtures and the start of the tutorial notebook.

## Goal

See what was built or loaded, before any physics runs: the shape, which component and material each panel belongs to, and which way every outward normal points. This is plot level 1 (D-61); levels 2 (the flow) and 3 (the Earth) will add traces to the same figure. plotly only, with no matplotlib fallback (D-62, D-64).

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/plots/spacecraft.py` | new: `plot_panel_set_3d` and three helpers to write; `_import_plotly` and `_largest_dimension_m` written | user (plotting), Claude (template, two helpers) |
| `tests/plots/test_spacecraft.py` | 12 tests, skipped without plotly | Claude |
| `tests/conftest.py` | new: shared fixtures `unit_cube_triangles_m` and `unit_cube_panel_set` | Claude |
| `tests/aero/test_geometry.py` | closing A3a: degenerate triangles at index 0, and alone | Claude |
| `notebooks/aero_tutorial.ipynb` | new: the running tutorial, sections 1–4 | Claude |
| `docs/decisions.md` | D-64 (no fallback), D-65 (tutorial notebooks) | Claude |

## The function and its helpers

```python
def plot_panel_set_3d(panel_set, *, color_by="component", show_normals=True,
                      normal_length_m=None, show_body_axes=True, figure=None) -> plotly Figure
```

| Function | Who | Does |
| --- | --- | --- |
| `plot_panel_set_3d` | user | the seven numbered steps: check, figure, mesh, normals, axes, layout, return |
| `_add_mesh_traces` | user | one `Mesh3d` per component or material, named, coloured, flat-shaded, with hover text |
| `_add_normal_traces` | user | one `Scatter3d` of lines (start, end, None per panel) and one of tip markers, in one legend group |
| `_add_body_axes_traces` | user | three named, coloured lines from the origin with labels |
| `_largest_dimension_m` | Claude | the spacecraft's largest extent, to scale normals and axes |
| `_import_plotly` | Claude | imports `plotly.graph_objects` or raises with the install command |

Trace names are module constants (`NORMALS_TRACE_NAME`, `NORMAL_TIPS_TRACE_NAME`, `BODY_AXIS_TRACE_NAMES`), so tests and later plot levels can find the traces.

**Normals.** They start at the centroids when the set has positions, with length `normal_length_m`, or 10% of the largest dimension by default. A macro model without positions has its normals drawn from the origin, panel i with length `largest dimension × area_i / largest area`. Its title then carries `NO_POSITIONS_NOTE`.

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | plotly: 3-D mesh plots (`Mesh3d`: `x`, `y`, `z`, `i`, `j`, `k`, `flatshading`, `color`, `hovertext`) | the triangles | 15 min |
| 2 | plotly: 3-D line and scatter plots (`Scatter3d` with `mode="lines"`, `"markers"`, `"lines+text"`) | normals and axes; `None` breaks a line into segments | 10 min |
| 3 | plotly: 3-D axes (`layout.scene`, `aspectmode`) | true proportions | 5 min |
| 4 | plotly: legends (`name`, `showlegend`, `legendgroup`) | clicking a name hides its traces | 5 min |
| 5 | `notebooks/aero_tutorial.ipynb`, sections 1–4 | what the finished figures should show | 10 min |

## Work order

1. `_add_body_axes_traces`: the smallest; lets you see a figure at once.
2. `_add_normal_traces`: build the x, y and z lists with `None` between segments.
3. `_add_mesh_traces`: one trace per name. Each triangle's corners can be its own three points (flatten the selected `triangle_vertices_m` to (3n, 3)), so i, j, k are simply 0, 1, 2, then 3, 4, 5, and so on.
4. `plot_panel_set_3d`: tie them together, following its numbered steps.
5. Run the notebook and look at every figure: all normals should point outward.

## Tests

At the start: 11 failed, 130 passed in the fast suite. Every failure is a `NotImplementedError` from `plot_panel_set_3d`; the import test passes already. Against a scratch implementation kept out of the repository, all 141 pass and every notebook cell runs.

| Test | Checks |
| --- | --- |
| mesh per component | a `Figure`, with mesh traces named `body` and `end_caps` |
| colour by material | mesh traces named `aluminium` and `solar_cell` |
| every triangle | the mesh traces hold 12 triangles in total |
| normals | 3N points in the line trace; tips at centroid + 0.25 × normal for `normal_length_m=0.25` |
| hide normals | no normal traces with `show_normals=False` |
| body axes | three named traces; none with `show_body_axes=False` |
| macro model | no mesh; tips from the origin with lengths in the ratio of the areas; the note in the title |
| proportions | `scene.aspectmode == "data"` |
| figure passed in | traces added to it, and it is returned |
| bad colouring | `ValueError` mentioning the options |
| lazy import | importing the module does not load plotly (fresh interpreter) |
| missing plotly | `ImportError` with the install command |

## Traps

- **Trace names matter.** The tests find traces by the module's constant names; use the constants, not new strings.
- **One line trace for all normals.** Adding a trace per normal makes the legend unusable and slows the figure; put `None` between segments instead.
- **Arrays versus lists.** `Scatter3d` accepts lists with `None` in them; a numpy float array cannot hold `None`, so build the line coordinates as lists or as an object array.
- **Equal proportions.** Without `aspectmode="data"`, plotly stretches each axis to fill the box, and a flat panel can look like a cube.
- **Hover text.** Give each mesh trace one text entry per triangle and set `hoverinfo="text"` (or a `hovertemplate`), or plotly shows only coordinates.

## Done when

All 12 tests in `tests/plots/test_spacecraft.py` pass, the fast suite shows 141 passed, `ruff format --check .` and `ruff check .` pass, and every figure in the notebook shows every normal pointing outward. Then send `spacecraft.py` for review.
