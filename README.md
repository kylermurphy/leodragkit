# leodragkit

Satellite drag in low Earth orbit: thermospheric density, spacecraft aerodynamics and drag-focused orbit propagation, for any satellite.

```python
import leodragkit as ldk
```

> **Status: skeleton (task T-00).** The package installs and `ldk --help` runs; no features are built yet. Every other command and API call below is **planned**: names and arguments are settled in each task's plan and may change. Progress is tracked in [`docs/tasks.md`](docs/tasks.md).

## What it does

leodragkit covers both sides of the drag equation, with B = Cd·A/m:

- **Atmosphere: density models behind one interface.** It covers NRLMSIS 2.1 and NRLMSISE-00 (through `pymsis`) and the models developed in den_pcaxg (through a separate model package). JB2008 is planned.
- **Spacecraft: `aero`.** It computes a physical Cd·A(t) and B(t) from a flat-panel model of the satellite, its attitude quaternions and the atmosphere's temperature and composition (a Sentman/DRIA panel method). It works on its own, for example to give contigo_edr a time-varying B for effective-density retrieval.
- **Orbit and drag (with Orekit):**
  - start states from a state vector or fitted to TLEs;
  - propagation with drag;
  - comparison with observations, through the orbit-mean altitude;
  - ballistic-coefficient estimation per density model;
  - ensemble decay and reentry forecasts that replay historical space weather.

Reentry forecasting is one use case, not the purpose of the package.

Each part works on its own. leodragkit is a refactor of `swift_reentry`, the Swift Observatory reentry forecast, generalised to any satellite in low Earth orbit.

## Installation

```bash
conda env create -f environment.yml
conda activate leodragkit
pip install -e .
pytest -m "not slow and not network"
```

Pinned versions and the reasons for them are in `environment.yml`.

Planned: the separate density-model package (name to be decided) is added to the environment when it exists, and the main config will give the location of Orekit's data.

## Configuration (planned)

One **main config**, kept outside the repository, says where data and outputs live:

```
<data_root>/      downloads (TLEs, SP3, attitude) and caches, under the providers' own file names
<output_root>/    saved results: <output_root>/<workflow_name>/<run_id>/
```

Because data files keep the providers' names, files already downloaded by other tools can be reused. A file is downloaded again only when the remote copy is newer.

Each workflow takes typed settings. These can be built in Python or loaded from a YAML file.

## Two ways to work

The same workflow functions serve research and production:

- **In a notebook or script**, call the API. Results are Python objects, written to disk only when you ask.
- **For production runs**, use the `ldk` command. It calls the same function and always saves the result with a `manifest.json`, which records the settings, every input file (path, size, modification time, SHA-256), the code version and the seeds.

A saved run loads back as the same object a fresh computation returns.

### Planned workflows

| Workflow | Command | What it does |
|---|---|---|
| update data | `ldk update-data` | download new TLEs (Space-Track) and space-weather data |
| drag area from attitude | `ldk drag-area-from-attitude` | Cd·A(t) and B(t) from geometry, attitude and the atmosphere |
| estimate ballistic coefficients | `ldk estimate-ballistic-coefficients` | B per density model, from TLEs or states; `constant` or `scaled_aero` mode |
| validate ballistic coefficients | `ldk validate-ballistic-coefficients` | check estimated B on independent windows |
| fit start state | `ldk fit-start-state` | a start state fitted to recent TLEs |
| compare with observations | `ldk compare-with-observations` | propagate and compare orbit-mean altitudes with observations |
| ensemble forecast | `ldk ensemble-forecast` | decay or reentry ensemble over historical space-weather futures |
| reentry forecast | `ldk reentry-forecast` | the full chain: update data, fit start state, estimate B, run the ensemble, summarise |

Example, as planned:

```bash
ldk estimate-ballistic-coefficients --norad-id 28485 --start 2026-09-01 --end 2026-10-20
```

```python
result = ldk.workflows.estimate_ballistic_coefficients(...)   # returns a result object
result.table                                                    # B per density model, with uncertainty
ldk.workflows.save_ballistic_coefficients(result, output_directory)   # only if you want it saved
```

The ensemble forecast and the ballistic-coefficient Monte Carlo take hours. They require an output folder, so an interrupted run can resume.

Space-Track credentials are typed at a prompt and never stored. For unattended runs, refresh the TLE cache first with `ldk update-data`.

## Package layout

```
leodragkit/
  io/          orbit data: TLEs, SP3, attitude
  density/     the DensityModel interface, MSIS
  aero/        flat plates, panel geometry, attitude, Cd·A(t) and B(t)
  orbit/       everything that needs Orekit
  forecast/    ensemble members, runner, summary
  workflows/   one module per workflow
  cli.py       the `ldk` command
```

`aero` depends only on numpy and scipy, so other programs can use it without Orekit or the density models.

## Documentation

| Document | Contents |
|---|---|
| [`docs/tasks.md`](docs/tasks.md) | the order of work and its status |
| [`docs/decisions.md`](docs/decisions.md) | every design and science decision, with its reason (D-NN) and open questions (Q-NN) |
| `docs/code_tour.md` | reading guide to the code, module by module (written as code lands) |
| `docs/methods/` | method write-ups, starting with the drag-coefficient primer |
| `docs/results_log.md` | results of reported runs |
| [`CLAUDE.md`](CLAUDE.md) and `.claude/` | the working rules for contributors and for Claude Code |

## Licence

MIT (D-32). The aero code is written from the published equations, not translated from ADBSat's GPL-3 code, so it is compatible with this licence (D-28).
