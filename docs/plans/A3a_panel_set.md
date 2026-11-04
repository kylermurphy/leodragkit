# A3a: `PanelSet`, the one geometry the solver sees

**Status: done 2026-10-30.** All tests pass; triangle maths written by the user. The review found a degenerate triangle at index 0 slipping through (`np.any` on `np.where`'s indices); fixed, and covered by new tests.

Step plan for task A3a in `docs/tasks.md`. Read `docs/plans/A3_geometry_overview.md` first: it explains where this step sits among A3a, A3p, A3b, A3c and A3d. Mode: the user writes the triangle maths; Claude wrote the dataclass, the constructors, the validation and the tests.

## Goal

Build `PanelSet` (D-41, D-56), the type every later geometry step produces and every solver stage reads, in two ways:

- **from triangles:** normals, areas and centroids derived from the corners;
- **from bare panels:** normals, areas and optional centroids, as in a macro-model table.

Validate it whenever one is created, so an invalid `PanelSet` cannot exist.

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/aero/geometry.py` | new: `TriangleProperties`, `PanelSet`, `compute_triangle_properties` (to write), `panel_set_from_triangles`, `panel_set_from_panels`, validation | Claude; user writes `compute_triangle_properties` |
| `tests/aero/test_geometry.py` | 23 tests | Claude |
| `docs/decisions.md` | D-63: rounded macro-model normals | Claude |
| `docs/tasks.md`, `docs/code_tour.md` | A3a status and entries | Claude |

No existing code to reuse. The libraries needed are `np.cross`, `np.linalg.norm` and `np.mean`.

## The type

```python
@dataclass(frozen=True)
class PanelSet:
    outward_normals: np.ndarray        # (N, 3) unit vectors, body frame
    areas_m2: np.ndarray               # (N,) > 0
    component_ids: np.ndarray          # (N,) integers indexing component_names
    material_ids: np.ndarray           # (N,) integers indexing material_names
    component_names: tuple[str, ...]
    material_names: tuple[str, ...]
    source: str                        # where the panels came from, for provenance
    centroids_m: np.ndarray | None = None          # (N, 3); None for macro models without positions
    triangle_vertices_m: np.ndarray | None = None  # (N, 3, 3); None unless built from triangles
```

Its properties are `panel_count`, `has_positions` and `has_triangles`. `__post_init__` runs the validation every time a `PanelSet` is created, however it was built.

## What to write: `compute_triangle_properties`

For each triangle with corners v₀, v₁, v₂, counter-clockwise seen from outside:

```
cross = (v₁ − v₀) × (v₂ − v₀)        area = |cross| / 2
outward normal = cross / |cross|      centroid = (v₀ + v₁ + v₂) / 3
```

The steps in the template:

1. check the array with `_as_finite_array(..., trailing_shape=(3, 3))`;
2. compute the edge vectors and their cross product;
3. compute the areas, then the degenerate check: an area at most `DEGENERATE_RELATIVE_AREA` times the longest edge squared raises a `ValueError` naming the first such triangle's index;
4. compute the normals;
5. compute the centroids.

Return a `TriangleProperties`.

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | `docs/plans/A3_geometry_overview.md` | where A3a sits; what it hands on | 10 min |
| 2 | `docs/aero_plan.md`, §3a (the `PanelSet` row) and §5 | the contract this step fixes | 10 min |
| 3 | `.claude/rules/aero.md`, "Geometry conventions" | winding, degenerate triangles, units | 5 min |
| 4 | Any reference on the cross product and the right-hand rule | why corner order sets the normal's direction, and why \|cross\| is twice the area | 15 min |
| 5 | numpy documentation for `np.cross` and `np.linalg.norm` (`axis`, `keepdims`) | vectorising over N triangles | 10 min |

## Tests

At the start: 13 failed, 111 passed in the fast suite. Every failure is a `NotImplementedError` from `compute_triangle_properties`. The macro-model tests already pass, because they don't need triangles. Against a scratch solution kept out of the repository, all 124 pass.

| Group | Tests |
| --- | --- |
| Triangle maths | a right triangle's normal (+z), area (0.5) and centroid; reversed order flips the normal; doubling the size quadruples the area; a unit cube has total area 6 and every normal points away from its centre; random triangles match trimesh to 1e-12 (skipped without trimesh) |
| Bad input | collinear and repeated corners raise, naming the triangle's index; wrong shapes and NaN raise naming `triangle_vertices_m` |
| From triangles | a cube gives 12 panels with positions and corners; component and material ids are kept per panel |
| Macro models | a table without positions is accepted and says so; rounded normals are normalised; a normal of length 0.9 raises |
| Validation | zero area, ids out of range or not integers, duplicate or empty names, wrongly shaped centroids and an empty source each raise naming the field; a `PanelSet` whose normals disagree with its triangles cannot be created |

## Traps

- **Corner order.** `np.cross(v₁ − v₀, v₂ − v₀)` gives the outward normal only for counter-clockwise corners; swapping the two edges flips it. The reversed-order test catches this.
- **Shapes.** `np.linalg.norm(cross, axis=1)` gives (N,); dividing (N, 3) by it needs `[:, np.newaxis]` or `keepdims=True`.
- **The degenerate check uses all three edges.** A triangle can have two long edges and a tiny area, so compare the area with the square of the longest of v₁ − v₀, v₂ − v₀ and v₂ − v₁.
- **Validation calls your function.** A `PanelSet` built from triangles is checked against `compute_triangle_properties` when it is created, so the constructor tests stay red until your function works.

## Done when

All 23 tests in `tests/aero/test_geometry.py` pass, the fast suite shows 124 passed, and `ruff format --check .` and `ruff check .` pass. Then send `geometry.py` for review. A3p, the 3-D plot, comes next.
