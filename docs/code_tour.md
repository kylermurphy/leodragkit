# Code tour

A reading guide to leodragkit, module by module, in the order to read them. Each entry says what the module does, where it sits in the workflows, and what to read first. Updated in the same step as the code (CLAUDE.md, "Documentation").

## Start here

1. `README.md`: what the package does and how it is used.
2. `CLAUDE.md`: the layout and the import order of the subpackages.
3. `docs/decisions.md`: why things are the way they are.

## Modules

The skeleton and the main config exist so far (tasks T-00, T-01):

- `leodragkit/__init__.py`: the package version. It imports no subpackage, so `import leodragkit` stays light.
- `leodragkit/config.py`: the main config (D-33 to D-35). Read `load_main_config` first: it reads the YAML, checks every key and path before creating any missing directory, and returns a frozen `MainConfig`. `create_main_config` writes a new file and never overwrites one.
- `leodragkit/cli.py`: the `ldk` command. It has no commands yet; one is added with each workflow.
- `leodragkit/<subpackage>/__init__.py`: one docstring each, saying what the subpackage will hold and what it may import.
- `tests/test_package.py`: the installation, the `ldk` command, and the import rules D-04 and D-05.
- `tests/test_config.py`: the main config, one test per rule, each a usage example.
- `leodragkit/aero/flat_plate.py` (task A1, being written): one flat plate in free-molecular flow. Read `compute_reflected_speed_ratio` (how fast molecules leave the surface), then `compute_sentman_flat_plate_coefficients` (pressure, shear and drag, returned as a `FlatPlateCoefficients`). Method: the drag-coefficient primer, steps 2–3; sign convention D-50; precision note R-03. Step plan and reading list: `docs/plans/A1_flat_plate.md`.
- `tests/aero/test_flat_plate.py`: structural checks of the plate, plus 50-digit precision references for back faces.
