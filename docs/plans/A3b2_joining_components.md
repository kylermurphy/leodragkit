# A3b2: Joining components into one `PanelSet`

Step plan for task A3b2 in `docs/tasks.md`; part of A3 (`docs/plans/A3_geometry_overview.md`). Mode: the user writes `join_components`; Claude wrote `Component`, the tests, notebook section 6 and the documentation.

## Goal

Turn a spacecraft's placed parts (a bus, deployed panels, an antenna) into one `PanelSet`, with each triangle tagged by its component and material (D-70). This is what the solver, the plots and A3b3's per-component orientation checks all read.

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/aero/geometry_builder.py` | `Component` (written, validated); `join_components` (to write) | Claude; user |
| `tests/aero/test_geometry_builder.py` | 12 tests for A3b2 | Claude |
| `notebooks/aero_tutorial.ipynb` | section 6: a 3U CubeSat with two deployed panels and an antenna | Claude |
| `docs/decisions.md` | D-70 | Claude |

## The types

```python
@dataclass(frozen=True)
class Component:
    name: str                        # unique within a spacecraft
    material: str                    # one material per component
    triangle_vertices_m: np.ndarray  # (n, 3, 3), already placed in the body frame

def join_components(components: Sequence[Component], source: str) -> PanelSet
```

A part with two materials (a bus with solar cells on two faces) is two components. The pose is applied before a `Component` is made, so joining never deals with poses.

## What to write: `join_components`

1. At least one component, and unique component names: raise a `ValueError` naming any repeat.
2. Material names: each once, in order of first appearance.
3. Ids per triangle: for component c with n triangles, n copies of c's index and n copies of its material's index.
4. Concatenate the triangles in component order, and build the result with `panel_set_from_triangles(triangles, component_ids, material_ids, component_names, material_names, source)`.

When it is written, remove the `# noqa: F401` comment on the `panel_set_from_triangles` import.

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | `leodragkit/aero/geometry.py`: `PanelSet` and `panel_set_from_triangles` | the inputs you are building | 10 min |
| 2 | numpy: `np.repeat`, `np.full`, `np.concatenate` | ids per triangle, and joining the triangles | 10 min |
| 3 | Python: `dict.fromkeys` (keeps first-appearance order), `list.index` | unique materials in order, and each component's material index | 5 min |
| 4 | `notebooks/aero_tutorial.ipynb`, section 6 | what the joined spacecraft should look like | 5 min |

## Tests

At the start: 7 failed, 172 passed in the fast suite. Every failure is a `NotImplementedError` from `join_components`; the five `Component` validation tests pass already. Against a scratch implementation kept out of the repository, all 179 pass and every notebook cell runs.

| Test | Checks |
| --- | --- |
| order and ids | 12 + 4 triangles in component order; names, materials, and ids per triangle; the source kept |
| shared materials | two aluminium components share one material id; materials in first-appearance order |
| area | the joined area is the sum of the parts |
| one component | identical to `panel_set_from_triangles` called directly |
| repeated name | raises, naming it |
| nothing, or no source | an empty list or an empty `source` raises |
| invalid `Component` | empty name or material, wrong shape, no triangles, NaN: each raises naming the problem |

## Traps

- **Ids are per triangle, not per component.** `component_ids` has one entry for every triangle; `np.repeat(np.arange(len(components)), counts)` does it in one call.
- **The material index is the material's position in the deduplicated list,** not the component's position.
- **Tuples, not lists, for names.** `PanelSet` stores names as tuples, and the tests compare with tuples.

## Done when

All 12 A3b2 tests pass, the fast suite shows 179 passed, `ruff format --check .` and `ruff check .` pass with the `noqa` comment removed, and notebook section 6 shows the CubeSat with both panels facing ±x.
