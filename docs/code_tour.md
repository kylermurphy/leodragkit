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
- `leodragkit/aero/geometry.py` (task A3a): `PanelSet`, the one geometry the solver sees. Read `PanelSet` (its fields and the checks run when one is created), then `compute_triangle_properties`, then the two constructors: `panel_set_from_triangles` and `panel_set_from_panels` (macro models). Overview of A3: `docs/plans/A3_geometry_overview.md`; step plan: `docs/plans/A3a_panel_set.md`.
- `tests/aero/test_geometry.py`: one triangle, a unit cube, random triangles against trimesh, and the validation rules.
- `leodragkit/plots/spacecraft.py` (task A3p): `plot_panel_set_3d`, an interactive plotly figure of a `PanelSet` with its normals and the body axes (D-61, D-62). plotly is imported only inside the function. Step plan: `docs/plans/A3p_spacecraft_plot.md`.
- `leodragkit/aero/geometry_builder.py` (task A3b1): primitives and poses. Read `Pose` and `make_pose` (where a component sits; rounded axes made exact), then `place_triangles`, then the primitives: `build_plate_triangles`, `build_box_triangles` (six placed plates) and `build_cylinder_triangles`, then `Component` and `join_components` (task A3b2), which make one spacecraft from its parts. Step plans: `docs/plans/A3b1_primitives_and_poses.md`, `docs/plans/A3b2_joining_components.md`.
- `leodragkit/aero/geometry_checks.py` (task A3b3): orientation checks, per component. Read `check_component` (weld, edges, signed volume; raises for closed components that are inconsistent or inward), then `check_panel_set_orientation` (run by `join_components`; warns about one-sided components facing the body), then `summarise_geometry` (a table per component, HTML in Jupyter). Step plan: `docs/plans/A3b3_orientation_checks.md`.
- `leodragkit/aero/frames.py` (task A4a, being built): `Attitude` (times and scale, `body_from_reference`, frame) and `OrbitStates` (positions and velocities in ITRF); `attitude_from_quaternions` applies the three conventions (scalar position, Hamilton or JPL, direction) and rejects quaternions not of length 1. `inertial_velocity_in_itrf`, `itrf_from_orbit_level` (Spire's orbit frame) and `attitude_from_law` build an attitude from the orbit; `attitude_in_itrf` turns Spire's orbit-frame attitude into ITRF; `common_epochs` and `check_same_epochs` match epochs exactly, never interpolating. `PanelFlowGeometry` (task A4b) holds, per epoch and panel, the speed, flow direction, cos δ and shear direction, checking û · t̂ = sin δ. Step plan: `docs/plans/A4a_attitude.md`.
- `tests/aero/test_flow_geometry.py`: a hand-worked cube and 45° plate; every inconsistency in `PanelFlowGeometry` named.
- `tests/aero/test_frames.py`: conventions against hand-worked rotations and a real Spire quaternion; the orbit frame by hand and for random states; the law; Spire's frame against the law; shared epochs.
- `leodragkit/aero/materials.py` (task A3c): `SurfaceMaterial`, a surface's wall temperature and accommodation, with no defaults.
- `leodragkit/aero/spacecraft.py` (task A3c): `Spacecraft` and `build_spacecraft`, which checks a description, builds each component and attaches the materials. Read `build_spacecraft` first; `_build_component` builds one checked entry. The format is in `docs/guides/describing_a_spacecraft.md`.
- `leodragkit/aero/repeated_warnings.py`: `warn_every_time`, for warnings Python must not hide as repeats.
- `leodragkit/time_scales.py` (task T-02): `Epochs`, the same instants as UTC, GPS and SPICE ET; build with `epochs_from_utc`, `epochs_from_gps` or `epochs_from_et` and the leap-second kernel. GPS ↔ UTC from the kernel's table; UTC ↔ ET through spiceypy. `aero` never imports it.
- `tests/test_time_scales.py`: fixed values (GPS − UTC, ET at J2000), round trips across the 2017 leap second, and leap-second handling; the test kernel is in `tests/conftest.py`.
- `leodragkit/io/http_download.py` (task T-02): `download_file`, the shared atomic downloader (a `.part` file, renamed when complete; timeout and User-Agent on every request).
- `leodragkit/io/records.py`: records readers return (D-83): `InputRecord` (path, size, modification time, SHA-256; D-15); `SatelliteStates` (task I1: epochs, positions and velocities in metres, frame label); `AttitudeRecords` (task I2: quaternions exactly as written, their conventions, a quality flag per epoch) and `keep_observed`. Both carry `input_records` and `dropped_records` (file, line) for every file read (D-87); `source_names` names them. Step plans: `docs/plans/I1_sp3_states.md`, `docs/plans/I2_spire_attitude.md`.
- `leodragkit/io/merging.py` (task I3): `merge_satellite_states` (each overlapping epoch from the file where it lies furthest from the ends), `merge_attitude_records` (observed values first), `overlap_differences`, and `read_sp3_files` / `read_spire_attitude_files` for lists of files. Step plan: `docs/plans/I3_merging.md`.
- `tests/io/test_merging.py`: overlapping records built by the tests; which file each epoch comes from, ties, provenance, warnings, attitude flags, versions refused.
- `leodragkit/io/text_files.py`: `text_lines`, the lines of a data file, plain or gzip, bzip2 or xz compressed, for every reader.
- `leodragkit/io/spire_attitude_files.py` (task I2): `read_spire_attitude_file(path, kernel)` → `AttitudeRecords`, pairing each `tim` with its `sca` and dropping bad, unmatched and repeated records (lines kept, one `AttitudeRecordsDroppedWarning`); every flag kept, checked against the file's version. Below it: `read_spire_attitude_header` (version → flag meanings, satellite, `sca`, GPS), `SPIRE_ATTITUDE_CONVENTIONS`, and the line parsers `_attitude_epoch` and `_attitude_quaternion`.
- `tests/io/test_spire_attitude_files.py`: attitude files written by the tests (versions 1.2 and 1.1); every reason a header or line is refused; each drop rule with its line numbers.
- `leodragkit/io/repeated_warnings.py`: io's `warn_every_time`, a marked duplicate of aero's (aero may not import outside aero).
- `leodragkit/io/sp3_files.py` (task I1): `read_sp3_file(path, kernel, satellite_id=None)` → `SatelliteStates`, pairing each `P` with its `V` and dropping bad, unmatched and repeated records (their lines kept, one `Sp3RecordsDroppedWarning`). Below it: `read_sp3_header` (version, velocity flag, frame name → `"ITRF"`, time system, satellite ids), `sp3_text_lines` (plain, gzip, bzip2 or xz), and the record parsers `_sp3_epoch` and `_sp3_vector`.
- `tests/io/test_sp3_files.py`: SP3 files written by the tests (Spire-like and IGS-like); every reason a header is refused; compressed files; each record rule; each drop rule with its line numbers.
- `leodragkit/io/spice_kernels.py` (task T-02): the leap-second kernel `naif0012.tls`, in the four-function template; never re-downloaded, its SHA-256 pinned. Step plan: `docs/plans/T-02_time_scales.md`.
- `leodragkit/io/geometry_files.py` (tasks A3c, A3d1, A3d2): `read_spacecraft_description_file`, YAML to a mapping; `read_macro_model_file` (A3d2), a CSV table of panels; `load_spacecraft_description`, which also reads the mesh files and macro-model table a description names.
- `leodragkit/io/mesh_files.py` (task A3d1): `read_stl_file` (binary and ASCII) and `read_obj_file`, triangles in metres, with the stored-normal check and `reverse_winding`. Step plan: `docs/plans/A3d1_meshes.md`.
- `tests/io/test_macro_model_files.py`: macro-model tables read, and every kind of bad table named by line and column.
- `tests/io/test_mesh_files.py`: STL and OBJ files written with known answers, read back; units, normals, reversed winding; trimesh as the oracle.
- `tests/aero/test_spacecraft_description.py`, `tests/io/test_geometry_files.py`: building from descriptions, every kind of mistake, the reader.
- `tests/aero/test_geometry_checks.py`: correct primitives pass, deliberately broken ones are caught; trimesh as the oracle.
- `tests/aero/test_geometry_builder.py`: areas and normals against hand formulas; closed primitives checked with trimesh for watertight, outward winding and volume.
- `tests/conftest.py`: shared fixtures; a unit cube as triangles and as a `PanelSet` with two components and two materials.
- `tests/plots/test_spacecraft.py`: smoke tests on the figure object, skipped without plotly.
- `notebooks/aero_tutorial.ipynb`: the running tutorial; one section per aero task (D-65).
- `tests/aero/test_sentman_independent_checks.py` (task A2): the Sentman plate checked against closed forms from the literature (Bird's sphere, Dey et al.'s DRIA plate and sphere, Cook's hyperthermal formula). The reference formulas sit at the top of the file. Step plan: `docs/plans/A2_independent_checks.md`.
