# Code tour

A reading guide to leodragkit, module by module, in the order to read them. Each entry says what the module does, where it sits in the workflows, and what to read first. Updated in the same step as the code (CLAUDE.md, "Documentation").

## Start here

1. `README.md`: what the package does and how it is used.
2. `CLAUDE.md`: the layout and the import order of the subpackages.
3. `docs/decisions.md`: why things are the way they are.

Code style is enforced by ruff (`ruff format .`, `ruff check .`), configured in `pyproject.toml`.

## Modules

The skeleton and the main config exist so far (tasks T-00, T-01):

- `leodragkit/__init__.py`: the package version. It imports no subpackage, so `import leodragkit` stays light.
- `leodragkit/config.py`: the main config (D-33 to D-35). Read `load_main_config` first: it reads the YAML, checks every key and path before creating any missing directory, and returns a frozen `MainConfig`. `create_main_config` writes a new file and never overwrites one.
- `leodragkit/cli.py`: the `ldk` command. It has no commands yet; one is added with each workflow.
- `leodragkit/<subpackage>/__init__.py`: one docstring each, saying what the subpackage will hold and what it may import.
- `tests/test_package.py`: the installation, the `ldk` command, and the import rules D-04 and D-05.
- `tests/test_config.py`: the main config, one test per rule, each a usage example.
- `leodragkit/aero/gas_surface.py`: the contract every gas-surface model meets, `FlatPlateCoefficients` (pressure, shear and drag of one-sided plates), with its sign convention (D-50, D-52). Read this before any model.
- `leodragkit/aero/gas_surface_sentman.py` (task A1): the Sentman model for one plate. Read `compute_reflected_speed_ratio` (how fast molecules leave the surface), then `compute_sentman_flat_plate_coefficients`. Method: the drag-coefficient primer, steps 2–3; precision note R-03. Step plan and reading list: `docs/plans/A1_flat_plate.md`. How the aero modules connect: `docs/aero_plan.md`, section 3a.
- `tests/aero/test_gas_surface_sentman.py`: structural checks of the plate, plus 50-digit precision references for back faces.
