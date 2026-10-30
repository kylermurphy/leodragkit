# Tasks and priorities

The order of work for leodragkit, at a high level. Each task's plan splits it into steps of about 150 lines of non-test code or less (CLAUDE.md, "How we work"). Decisions are cited as `D-NN` and open questions as `Q-NN` (`docs/decisions.md`).

**Updating this file.** Change a task's status when its last step is approved: `todo`, `in progress` or `done (date)`. Add new tasks at the end of their track. Reorder only with the user's approval. Results go in `docs/results_log.md`, not here.

## How the order was chosen

- **aero needs nothing else.** `aero` takes atmosphere values as arrays (D-04), so it can be built and tested before the rest of the package.
- **The orbit and forecast port waits on the model package.** MSIS needs F10.7 and ap drivers, and all space-weather I/O lives in the separate model package (D-11). M1 therefore comes before any density or orbit work.
- **aero comes first.** It is small, new code with no ports, so it tests the whole cycle (plan → approval → `step-implementer` → `step-reviewer` → report) before the large port starts. contigo_edr also gets B(t) early.

The tracks are interleaved or run one after the other, never in parallel.

## Setup

| ID | Task | Depends on | Size | Status | Notes |
|---|---|---|---|---|---|
| T-00 | Repository skeleton: `pyproject.toml` (name, `ldk` entry point, dependencies), `environment.yml`, empty subpackages with module docstrings, pytest markers, `docs/`, `.claude/` files, `.claude/settings.local.json` with swift_reentry in `additionalDirectories` | none | S | done (2026-10-27) | Still to confirm in a Claude Code session: reading swift_reentry works, editing it is refused. |
| T-01 | Main config: output directory and one directory per data source, typed and validated | T-00 | S | done (2026-10-28) | D-33 to D-36. Everything else reads it. |

## Track A: aero (first priority)

Plan and module layout: `docs/aero_plan.md`. Validation rungs V0–V7 are defined there.

| ID | Task | Depends on | Size | Status | Notes |
|---|---|---|---|---|---|
| A1 | `aero/gas_surface.py` (the contract) and `aero/gas_surface_sentman.py`: Sentman plate, returning the reflected-speed ratio and the pressure and shear coefficients (drag derived), with structural tests | T-00 | S | done (2026-10-30) | D-28, D-38, D-39, D-50, D-52, D-55. V0. Written by the user from the template |
| A2 | Independent checks of the plate: Bird / Dey sphere by quadrature; Dey eq. 2.3 = Sentman with k = 2/3; Sentman's hyperthermal limit and its fixed difference from Cook | A1 | S | in progress (template; user writing) | Q-04 (except k = 1/2, α < 1, which waits for A11). R-04. V1, V2 |
| A3 | Geometry: `PanelSet`, primitives (plate, box, cylinder), component descriptions and macro-model tables, materials; STL/OBJ and YAML readers in `io/` | A1 | M | todo | D-41, D-42. trimesh as test oracle. V3 |
| A4 | `frames.py` (`Attitude`, a simple attitude law, `PanelFlowGeometry`, fixed component poses) and `flow_conditions.py` (`AeroAtmosphere`, `FlowConditions`) | A3 | M | todo | D-27, D-42, D-44, D-53. Q-13 first |
| A5 | Constant `SurfaceInteraction`, `integration.py` and `drag_area.py`: force and moment vectors, drag, lift, side force, Cd·A, B(t), averaging; chunked over epochs, with a timing benchmark | A4 | M | todo | D-21, D-39, D-52, D-54. The workflow `drag_area_from_attitude` comes with it (W1). V2 meshed sphere, V3 |
| A6 | Shadowing: centroid projection with self-exclusion | A5 | M | todo | Plate-in-front-of-box, L-shape and convex-sphere cases. V3 |
| A7 | Connect to `AtmosphereState`, with the mixed-model warning | A5, D1 | S | todo | D-10, D-12 |
| A8 | `gas_surface_dria.py`: per-species Sentman, mass-weighted | A7 | S | todo | D-45. V1 |
| A9 | Accommodation: constant, and the Walker/Langmuir surface-coverage model | A8 | M | todo | Material surface-atom mass |
| A10 | `gas_surface_cll.py`: CLL plate (σ_n, σ_t), with constant and Walker accommodation | A9 | M | todo | D-46. V1, V2 |
| A11 | ADBSat comparison: reference numbers from ADBSat or ADBSat-PyVersion, run with explicit speeds | A6, A10 | S | todo | V4. Also reproduces the primer's k = 1/2 plate values at α < 1 (2.4380, 3.2737), closing Q-04 |
| A12 | Validation: Dey et al. GRACE and C/NOFS values; CHAMP and GRACE with TU Delft geometry, SPARTA tables and accelerometer densities | A11 | L | todo | Q-10. V5, V6 |
| A13 | Articulated components: hinge-angle series and Sun tracking | A12 | M | todo | D-42 |

## Model package (separate repository)

| ID | Task | Depends on | Size | Status | Notes |
|---|---|---|---|---|---|
| M1 | The model package: space-weather I/O with source flags, parquet feature cache, model loaders, the Protocol methods | T-00 | L | todo | D-11, D-19. It needs its own plan and rules. Name it first (Q-02). Designed in chat alongside Track A. |

## Track B: orbit and forecast

| ID | Task | Depends on | Size | Status | Notes |
|---|---|---|---|---|---|
| D1 | `density/interface.py` and `density/msis.py`: Protocol, `AtmosphereState`, MSIS with drivers from M1 | M1 | M | todo | D-10. Equivalence test against `swift_reentry/density/msis.py`. |
| B1 | `io/http_download.py` and `io/space_track_tles.py` | T-01 | M | todo | D-13, D-30. Check Space-Track's usage policy first. |
| B2 | `orbit/`: Orekit environment, atmosphere adapter, propagation, orbit-mean altitude | D1 | L | todo | Ports `orekit_env.py`, `atmosphere.py`, `propagate.py` and `compare.py`, over several steps. |
| B3 | Start states: from a state vector, and the TLE fit | B1, B2 | L | todo | D-14. `tle_state.py` (1,379 lines) splits into several steps. |
| B4 | B estimation, `constant` mode | B3 | L | todo | D-22. `ballistic.py` (2,507 lines): port only what the workflow uses. |
| B5 | Forecast: driver futures, members, runner, summary | B4, M1 | L | todo | D-18, D-19. Requires an output folder; resumes. |

## Workflows and command line

| ID | Task | Depends on | Size | Status | Notes |
|---|---|---|---|---|---|
| W1 | Workflows and `ldk` commands, added as each building block lands; the composite `reentry_forecast` last | per workflow | S each | todo | D-16, D-17. The first is `drag_area_from_attitude`, with A4. |

## Later (parked, not forgotten)

| Task | Waits on |
|---|---|
| `scaled_aero` B-estimation mode | Q-06 (time-varying drag coefficient in Orekit) |
| aero: coefficient databases and interpolation, faster shadowing, Numba/JAX, constellations, multiple reflections, analytic components, winds | D-43; a workflow that needs them |
| SP3 reader, and start states from SP3 | a need in a workflow |
| Attitude file reader | a real file to test against (D-27) |
| JB2008 | a decision on drivers for ensemble members |
| Environment-variable Space-Track credentials | Q-07 |
