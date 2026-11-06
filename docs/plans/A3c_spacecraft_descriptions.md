# A3c: Spacecraft descriptions (materials, YAML, poses)

Step plan for task A3c in `docs/tasks.md`; part of A3 (`docs/plans/A3_geometry_overview.md`). Mode: the user writes `_build_component`; Claude wrote the rest: materials, `Spacecraft`, the description checks, the rotation form of a pose, the io reader, the example file, the guide, the tests, notebook sections 8 and 9, and the documentation.

## Goal

Describe a spacecraft in a short YAML file instead of Python, and turn it into a checked `Spacecraft` (panels, materials, mass) using everything A3b built (D-72 to D-75). Most users will describe spacecraft this way, so every error names its place in the file, and a guide explains the format with worked examples (`docs/guides/describing_a_spacecraft.md`).

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/aero/materials.py` | new: `SurfaceMaterial` | Claude |
| `leodragkit/aero/spacecraft.py` | new: `Spacecraft`, `build_spacecraft`, the checks, `SpacecraftDescriptionWarning`; `_build_component` to write | Claude; user |
| `leodragkit/aero/geometry_builder.py` | `turn_pose_about_own_axis`, `make_pose_from_rotation` | Claude |
| `leodragkit/aero/repeated_warnings.py` | new: `warn_every_time`, moved out of `geometry_checks.py` now that two modules use it | Claude |
| `leodragkit/io/geometry_files.py` | new: `read_spacecraft_description_file` | Claude |
| `config/geometry/cubesat_3u_example.yaml` | the example spacecraft | Claude |
| `docs/guides/describing_a_spacecraft.md` | the guide | Claude |
| tests | `tests/aero/test_spacecraft_description.py`, `tests/io/test_geometry_files.py`, rotation-pose tests in `tests/aero/test_geometry_builder.py` | Claude |
| `notebooks/aero_tutorial.ipynb` | section 8 (plates in each plane, tilts, all three pose forms), section 9 (the example file, a mistake, a spare material) | Claude |

## What to write: `_build_component(entry, default_resolution_m)`

By the time it is called, the entry has been checked: right keys for its shape, positive sizes, a defined material, a pose with `centre_m` and the axes, a turn, or both (D-76). So it only builds:

1. **Resolution:** the entry's own `max_edge_length_m` if present, else `default_resolution_m`.
2. **Triangles:** `PRIMITIVE_BUILDERS[entry["shape"]]` with the shape's arguments.
   - box: `*entry["size_m"]`;
   - plate: `*entry["size_m"]` and `two_sided=entry.get("two_sided", False)`;
   - cylinder: `entry["radius_m"]`, `entry["height_m"]` and `capped=entry.get("capped", True)`;
   - every shape: `max_edge_length_m=` the resolution.
3. **Pose:** `_pose_from_entry(entry["pose"])` (written), which handles all three forms.
4. **Return** `Component(entry["name"], entry["material"], place_triangles(triangles, pose))`.

Then remove the `# noqa: F401` on the `place_triangles` import.

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | `docs/guides/describing_a_spacecraft.md` | the format you are building from, and what it promises users | 20 min |
| 2 | `config/geometry/cubesat_3u_example.yaml` | a complete description | 5 min |
| 3 | `leodragkit/aero/spacecraft.py`: `build_spacecraft` and `_check_component_entry` | what is already checked before your function runs | 10 min |
| 4 | Python: `dict.get` with a default; unpacking a list into arguments with `*` | the shape's arguments | 5 min |
| 5 | `notebooks/aero_tutorial.ipynb`, sections 8 and 9 | what the result should look like | 10 min |

## Tests

At the start: 13 failed, 229 passed in the fast suite. Every failure is a `NotImplementedError` from `_build_component`; the checks of keys and values already pass, because they run first. Against a scratch implementation kept out of the repository, all 242 pass and every notebook cell runs.

| Group | Tests |
| --- | --- |
| Rotation poses | +30° about x turns z towards −y; a rotation equals the same orientation written as axes; a turn after axes is about the part's own axis (20° about a panel's long side); turning an unrotated pose is the turn-only form; a turn about the normal spins a plate in its plane; the axis length doesn't matter; a zero or malformed axis raises |
| Building | a description gives a `Spacecraft` with its parts, materials and mass; materials line up with the material names; the rotation form is used; axes then a turn are used; a component's resolution override works; the example file builds and passes every orientation check |
| Mistakes | fourteen kinds, each raising with its place: an unknown or missing top-level key, a bad mass, no components, an unknown shape, a misspelt key, wrong `size_m` length, a negative size, a non-number radius, an undefined material, a non-boolean flag, a pose with no orientation, a pose with half of each pair, non-perpendicular axes; also a bad material property and a repeated component name |
| Spare material | defined but unused: warns, naming it, and is left out |
| Reader | a file is read as a mapping; a missing file, invalid YAML and a non-mapping each raise |

## Traps

- **Unpacking sizes.** `build_box_triangles(*entry["size_m"], max_edge_length_m=…)` passes the three sizes as the three positional arguments; without `*` the list would be one argument.
- **Defaults for the flags.** Plates are one-sided and cylinders capped unless the entry says otherwise: use `entry.get("two_sided", False)` and `entry.get("capped", True)`.
- **Resolution `None` is a value.** The top-level `max_edge_length_m: null` means the coarsest mesh. `entry.get("max_edge_length_m", default_resolution_m)` handles both cases.
- **Test file names must be unique across `tests/`.** pytest imports test files by their bare names; `tests/aero/test_spacecraft.py` clashed with `tests/plots/test_spacecraft.py`, hence `test_spacecraft_description.py`.

## Done when

All A3c tests pass, the fast suite shows 242 passed, `ruff format --check .` and `ruff check .` pass with the `noqa` removed, and notebook sections 8 and 9 run: the placement gallery shows each plate facing the way its pose says, and the example file builds with every summary row "ok".
