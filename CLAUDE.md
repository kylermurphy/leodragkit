# CLAUDE.md: leodragkit

Rules for Claude (and humans) working on this project. Read this file at the start of every session. Topic rules in `.claude/rules/` load when you work in their folders; decisions and their reasons are in `docs/decisions.md` (cited as `D-NN`).

## What this project is

`leodragkit` (imported as `import leodragkit as ldk`) is a Python package for **satellite drag** in low Earth orbit, for any satellite, from state vectors, SP3 files or TLEs. It covers both sides of drag:

- **Atmosphere**: thermospheric density models behind one Protocol (NRLMSIS through `pymsis`; the den_pcaxg models through a separate model package; JB2008 later).
- **Spacecraft** (`aero`): a physical Cd·A(t) and B(t) from panel geometry, attitude and the atmosphere state, used on its own (for example by contigo_edr) or in B estimation.

The **orbit and drag** workflows use Orekit: start states, propagation with drag, comparison with observations (orbit-mean altitude), ballistic-coefficient estimation per density model, and ensemble decay or reentry forecasts. Reentry is one use case, not the purpose of the package.

The old `swift_reentry` code is the **reference**: read it, cite it, port from it, never edit it. It is a sibling folder listed in `additionalDirectories` in `.claude/settings.json`.

---

## How we work: slowly, one step at a time

The user wants to read and understand every change. Speed is not a goal; clarity is.

1. **Plan, then wait.** Before writing code, write a short plan and stop for approval:
   - the goal, in one or two sentences, and who writes the code (see below);
   - the files you will create, change or delete;
   - the existing code you will reuse (`path/file.py::function`), from this repo or from `swift_reentry`;
   - the standard or third-party modules you will use instead of writing code;
   - what you will delete;
   - the tests you will add;
   - the expected size of the change;
   - any subagent you will use, and for what.
2. **Small steps.** Aim for under about 150 lines of new non-test code per step. If a step is bigger, split it and say how.
3. **Implement only what was approved.** Anything else you notice goes in the report as a suggestion, not into the code.
4. **Explain, then wait.** After implementing, report (format at the end of this file) and stop. The user reads the code before the next step.
5. **One change at a time.** No parallel subagents. Read-only subagents run only when the plan names them; the `step-implementer` runs only on a plan the user has approved (see "Subagents").
6. **Never claim what you did not check.** Paste real test output. Say "not run" when something was not run.

### Who writes the code

Every plan states one of two modes; if the user does not say, ask.

**Claude writes it** (the default): steps 1–4 above.

**The user writes it from a template.** After the plan is approved, provide, and stop:
- a **template** for each new file: the module docstring, imports, and every function as a signature with type hints and a full docstring (purpose, parameters with units, returns, raises), its body `raise NotImplementedError("...")` with a one-line hint of the approach and the reused code to look at (`path::function`);
- the **tests first**: the tests the code must pass, runnable now and failing;
- **pointers**: the library functions and old code worth reading, and any trap to avoid.

When the user asks for a review: run the tests and paste the output; list findings against this file, the rules files and `docs/decisions.md`, each with the line, the problem and a suggested fix; **do not rewrite the user's code** unless asked; say briefly what is good as well.

A step can mix modes; the plan says which function is whose.

**Always stop and ask before:**
- adding a dependency;
- changing anything under a "Science conventions" heading, in this file or in `.claude/rules/`;
- changing an interface file (`leodragkit/density/interface.py`, and any file the plan marks as an interface);
- deleting or renaming a public function, config key or output file;
- any run longer than a few minutes;
- changing the layering or API shape below.

---

## Principles

1. **YAGNI.** Build only what the current step needs. No options nobody uses, no abstract base classes or registries until there are two real implementations, no caching until a measurement shows it is needed, no "for later" parameters.
2. **DRY, with judgement.** At the **second** occurrence of a pattern, write `# DUPLICATE OF path::function` and mention it in the report. Extract at the **third**, or earlier when the copies must always change together. Do not merge code that only looks alike.
3. **Search first.** Before writing any function, class or helper, search, and say in the plan what you searched: this repository; `swift_reentry`; the standard library; the approved dependencies; then other well-maintained libraries (ask before using anything not mainstream).
4. **Cite existing code.** Name what you reuse in the plan, the report and the docstring (`Adapted from swift_reentry/compare.py::window_mean; simplified: ...`), with what you changed and why.
5. **Ask before building.** If unsure whether something exists or may be used, stop and ask.
6. **Fail fast.** Raise a specific exception saying **what** is wrong, **where** (file, key, time, member) and **how to fix it**. Validate at the boundaries (config, file reading, API entry points); trust validated inputs inside. No bare `except`, no silent defaults, fills or extrapolation. A fallback is allowed only when the config enables it **and** the output records it.
7. **Simple first.** Plain functions, dataclasses, explicit loops. Optimise only after a measurement, and report it. No metaprogramming, no decorators that hide control flow, no dense one-liners.
8. **Delete aggressively.** Every step lists what it removed. No commented-out code, dead flags or compatibility shims. Port only what the agreed workflow uses.
9. **Semantic naming.** Verbose names for variables, parameters, functions, config keys and output columns. Units in names (`altitude_km`, `velocity_m_per_s`, `ballistic_coefficient_m2_per_kg`, `density_kg_per_m3`); `_utc` for timestamps, `_s`, `_h`, `_days` for durations. Functions are verbs, booleans are questions (`is_reentered`). Single letters only for maths in a short scope, matching a formula in the docstring.
10. **Readable in one sitting.** Functions do one thing and fit on a screen (about 40 lines). Every module starts with a docstring (what it does, where it sits, what to read first); every public function has one (purpose, parameters with units, returns, raises, a short example where helpful). Type hints on every signature.
    - **Numbered step comments.** A function with more than one stage marks each stage with a numbered comment saying what it does and, when not obvious, why (`# 1. Read the file: the default location unless a path is given.`). A blank line separates the stages. Short single-stage functions need none.
    - **Comments explain why, in plain words.** A non-obvious choice states its reason, and cites its published source where there is one. Decision ids (`D-NN`) stay in the docs (`docs/decisions.md`, `docs/code_tour.md`, `.claude/rules/`), never in code, comments, docstrings or tests.
11. **Pure functions, I/O at the edges.** Computation takes inputs and returns outputs. Reading and writing happen in `load_*`, `read_*`, `download_*` and `save_*` functions. No hidden global state. Randomness comes from an explicit seed or `numpy.random.Generator`, and seeds are saved.
12. **Tests as examples.** Every public function gets a test that reads as a usage example. **Ported science gives the same answer**: add an equivalence test against the old function or a saved output, with a stated tolerance. Mark tests needing Orekit, local data, the network or more than 30 s (`orekit`, `data`, `network`, `slow`). Run the step's tests and the fast suite; paste the output.

---

## Dependencies

Approved: the standard library, `numpy`, `pandas`, `scipy`, `pyyaml`, `requests`, `pyarrow`, `orekit_jpype`, `pymsis`, `matplotlib`, `pytest`; the separate density-model package once it exists (D-11). One install, no optional extras (D-06).

Ask before adding anything else. Pin versions in `environment.yml`.

---

## Layout and layering

```
leodragkit/
  config.py  cli.py  provenance.py
  io/          orbit data only: TLEs, SP3, attitude (space weather comes from the model package)
  density/     DensityModel Protocol, MSIS, toy exponential model
  aero/        flat plate, panel geometry, attitude, Cd·A(t) and B(t)
  orbit/       everything that needs Orekit
  forecast/    ensemble science: driver futures, members, runner, summary
  workflows/   one module per task
```

- **Import order:** `io`, `density`, `orbit`, `forecast`, `workflows`, `cli`. A subpackage imports only from those before it (D-03).
- `aero` imports only numpy and scipy, and nothing from leodragkit (D-04).
- All JPype and Orekit code lives in `orbit/` (D-05).

---

## API, workflows and outputs

Three layers (D-16):

1. **Building blocks** in `io`, `density`, `aero` and `orbit` return in-memory results.
2. **Workflows** in `leodragkit/workflows/`, one per task, take typed settings and return one result object. They write files only when given an output folder. Each result type has `save_*` and `load_*` in the module that produces it, so a notebook gets the same object from a fresh run or a saved one. Composite workflows chain others in memory, never through files.
3. **Command line**: `ldk <workflow>` in `cli.py` takes simple flags or a config file, calls one workflow and always saves. Each command is a few lines. There is no `scripts/` folder.

- Config files are data: YAML loaded into typed dataclasses that the workflows accept. Notebooks call the API only.
- Every path comes from the main config, `~/.leodragkit/main_config.yaml` by default: one directory per data source, plus the output directory (D-33, D-34). Never hard-code a path.
- Outputs go to `<output_root>/<workflow_name>/<run_id>/` with one `manifest.json` (settings, input records, code version, seeds). A composite run keeps its stages as subfolders (D-17).
- Every input file is recorded at load time (path, size, modification time, SHA-256), and results carry those records (D-15).
- The ensemble forecast and the B Monte Carlo require an output folder and are the only workflows that resume (D-18).

---

## Porting from `swift_reentry`

Before porting a module, write a **port note** in the plan:
- what the old module does and which parts the agreed workflow uses;
- what to keep, simplify, drop, or replace with a standard or approved library;
- the equivalence test that will prove the science did not change.

The order of work is in `docs/tasks.md`.

---

## Subagents

Defined in `.claude/agents/`. They run one at a time, never in parallel (D-31):

- `reference-searcher` (sonnet, read-only): searches this repo, `swift_reentry`, the standard library and the approved dependencies for existing code; returns `path::function` candidates. Used while writing a plan.
- `step-implementer` (session model): implements one approved plan step, in the mode the plan names. It is given the approved plan verbatim. It stops and reports when anything is unclear, and never commits.
- `step-reviewer` (opus, fresh context, read-only): reviews a finished step against this file, the rules files and `docs/decisions.md`; runs the tests; reports findings. It may run commands but never edits files.
- `citation-checker` (sonnet, read-only): checks that every citation resolves to the cited work (DOI, or ISBN with edition); flags anything unverified.

**Cycle for each step:** plan (with `reference-searcher` if needed) → user approves → `step-implementer` → `step-reviewer` → the main session checks the diff, reruns the tests and reports to the user. The main session reviews every subagent result before acting on it.

---

## Documentation

Updated in the same step as the code:
- `README.md`: what the package does, each part on its own, and the workflows, both from the command line and as API calls;
- `docs/code_tour.md`: a reading guide, module by module, in reading order;
- `docs/decisions.md`: every science or design decision, dated, never edited afterwards (supersede instead);
- `docs/results_log.md`: every reported or acted-on run, with an id that docs and decisions cite;
- `docs/methods/`: method write-ups (for example the drag-coefficient primer), with no run results;
- module and function docstrings.

Never put an unverified citation in code or docs: every citation has authors, year and a DOI checked to resolve to the work. A book without a DOI may be cited by a verified ISBN with its edition, because table and equation numbers change between editions (D-29). A technical report with neither (for example Storch 2002) is cited by author, year, title, issuing organisation, every report number on its cover and its release statement, with a note of where the copy read came from (D-49).

---

## Report format at every stop

1. **What was done**, in two or three sentences.
2. **Files** created, changed and deleted, one line each.
3. **Reused or adapted code**, with `path::function` for each.
4. **Walkthrough**: the new code in reading order; for each function, what it does, why, its inputs and outputs with units, and what changed from the old code.
5. **How to check it yourself**: a command, a test or a small snippet.
6. **Test output**, verbatim.
7. **Duplicates noted, things deleted, suggestions not implemented.**
8. **Questions**, each with a recommendation.

When the user writes the code, the stop after the template reports items 1–3, the templates, the failing tests and the pointers; the stop after a review reports the test output and the findings.
