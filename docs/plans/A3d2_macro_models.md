# A3d2: Macro models (tables of panels)

Step plan for task A3d2 in `docs/tasks.md`; part of A3 (`docs/plans/A3_geometry_overview.md`). Mode: the user writes the row parsing in the table reader; Claude wrote the rest: header checks, the `MacroModelTable` type, the description wiring, the direct path, the example, the tests, notebook section 11, the guide's section 5b and the documentation.

## Goal

Read a spacecraft published as a table of flat panels (normal, area, material, optionally centre), as precise-orbit-determination macro models are, and build a `Spacecraft` from it. No triangles are invented, so there is no shadowing (D-78). The guide's section 5b says when that is enough (convex spacecraft without deployables; reproducing published results) and when it is not.

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/io/geometry_files.py` | `MacroModelTable`, `read_macro_model_file` (header checks written), `_macro_model_from_rows` (to write); `load_spacecraft_description` reads `macro_model.file` | Claude; user |
| `leodragkit/aero/spacecraft.py` | `build_spacecraft` accepts `macro_model` instead of `components`; `build_spacecraft_from_macro_model`; materials and the unused-material warning factored out for both forms | Claude |
| `config/geometry/cubesat_3u_macro_model.csv`, `.yaml` | the example: the 3U CubeSat's bus faces and its two panels, front and back, with centres | Claude |
| `config/geometry/grace_macro_model.csv`, `.yaml` | GRACE's eight flat surfaces, from Bettadpur (2012), GRACE 327-720, §I.5.3.5, checked against the rendered page; mass from §I.5.3.3; the boom left out | Claude |
| `tests/io/test_macro_model_files.py` | new: 11 tests | Claude |
| `tests/aero/test_spacecraft_description.py` | 6 tests for both paths | Claude |
| `notebooks/aero_tutorial.ipynb` | section 11: the example with centres, then without | Claude |
| `docs/guides/describing_a_spacecraft.md` | section 5b, "Macro models: panels without shapes" | Claude |

## What to write: `_macro_model_from_rows(rows, has_centroids, file_path)`

`rows` are dicts of strings, as `csv.DictReader` gives them; row r is on line r + 2 of the file, since line 1 is the header.

1. For each row: `component` and `material`, stripped of spaces. An empty one raises `ValueError(f"{file_path}, line {r + 2}, column component: …")`.
2. The numbers: `normal_x`, `normal_y`, `normal_z` and `area_m2`, plus the three centroid columns when `has_centroids`. Convert each with `float(value.strip())`, and raise naming the line and column if that fails (an empty field fails too).
3. Return a `MacroModelTable`:
   - tuples of names;
   - normals (N, 3) and areas (N,);
   - centroids (N, 3), or `None`;
   - `source=file_path.name`.

Physics checks (unit normals, positive areas) are not yours: `panel_set_from_panels` makes them when the spacecraft is built.

## Required reading

| # | What | Why | Time |
| --- | --- | --- | --- |
| 1 | `docs/guides/describing_a_spacecraft.md`, section 5b | what a macro model is, and the format | 10 min |
| 2 | Python's `csv` module: `csv.DictReader` (https://docs.python.org/3/library/csv.html#csv.DictReader) | each row as a dict keyed by the header | 10 min |
| 3 | `config/geometry/cubesat_3u_macro_model.csv` | a complete table | 2 min |
| 4 | `read_macro_model_file` in `geometry_files.py` | what is checked before your function runs | 5 min |

## Tests

At the start: 9 failed, 275 passed in the fast suite. Every failure is a `NotImplementedError` from `_macro_model_from_rows`. The checks of headers and the build-path tests that don't read a table already pass. Against a scratch implementation kept out of the repository, all 284 pass and every notebook cell runs.

| Group | Tests |
| --- | --- |
| Reading | a table with centroids, row by row; without centroids, `None`; spaces around values allowed |
| Bad tables | a missing column, an unknown column, one centroid column only, no rows, a non-number (line 3), an empty value, an empty name: each names the problem; a missing file raises |
| Building | the GRACE table builds (8 panels, total area 16.9163284 m², 487.2 kg, three materials, normals normalised); the example builds: 10 panels, no triangles, positions, three components, the right total area, every summary row "not checkable"; the direct path equals the description path; rounded normals are normalised and a bad one raises; an undefined material raises; components and a macro model together raise; an unread table says how to load it |

## Traps

- **Line numbers.** Row 0 is line 2 (the header is line 1); the tests check "line 3" for the second data row.
- **Empty fields.** `csv.DictReader` gives `""` for an empty field, and `float("")` raises, which is the error you want; make sure the message still names the line and column.
- **Tuples for names.** `MacroModelTable` stores names as tuples, like `PanelSet`.

## Done when

All A3d2 tests pass, the fast suite shows 284 passed, `ruff format --check .` and `ruff check .` pass, and notebook section 11 shows the macro model with its normals drawn from the panel centres, then from the origin without them, and GRACE.
