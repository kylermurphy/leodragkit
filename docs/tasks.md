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
| T-00 | Repository skeleton: `pyproject.toml` (name, `ldk` entry point, dependencies), `environment.yml`, empty subpackages with module docstrings, pytest markers, `docs/`, `.claude/` files, `.claude/settings.local.json` with swift_reentry in `additionalDirectories` | none | S | in progress | Check in the first session that subagents can read swift_reentry. |
| T-01 | Main config: data and output roots, typed and validated | T-00 | S | todo | Everything else reads it. |

## Track A: aero (first priority)

| ID | Task | Depends on | Size | Status | Notes |
|---|---|---|---|---|---|
| A1 | `aero/flat_plate.py`: Sentman/DRIA flat plate, with structural tests | T-00 | S | todo | The primer's first function, renamed to the naming rules (D-28). |
| A2 | Reproduce the primer's reference values independently | A1 | S | todo | Answers Q-04: Bird's sphere formula, and ADBSat if available. |
| A3 | `aero/panel_geometry.py` and `aero/attitude.py`: panel tables as data, quaternions with explicit conventions | A1 | M | todo | D-27. The first geometry is a box, then CHAMP. |
| A4 | `aero/drag_area.py`: Cd·A(t) and B(t), averaging option, composition from arrays | A3 | M | todo | D-21. contigo can use it from here. The workflow `drag_area_from_attitude` comes with it (W1). |
| A5 | Connect aero to `AtmosphereState`, with the mixed-model warning | A4, D1 | S | todo | D-12 |
| A6 | Validate aero on CHAMP: geometry and accelerometer densities | A5 | L | todo | Needs CHAMP data I/O and a verified geometry source. |

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
| SP3 reader, and start states from SP3 | a need in a workflow |
| Attitude file reader | a real file to test against (D-27) |
| JB2008 | a decision on drivers for ensemble members |
| Environment-variable Space-Track credentials | Q-07 |
