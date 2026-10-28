# Decision log

Every science and design decision that shapes leodragkit, in one place, with its reason and what was rejected. Method documents and docstrings describe *what* the code does; this log records *why*.

**Rules.** Add an entry whenever a science convention, a default that changes results, a design rule or a validation approach is decided. Entries are never edited afterwards: to reverse a decision, add a new entry that supersedes the old one and mark the old one `Superseded by D-NN`. Dates are when the decision was made. "User" means the project lead decided.

**Carried-over conventions.** The science conventions in CLAUDE.md come from `swift_reentry/docs/decisions.md`. Each one is entered here, citing its swift_reentry entry, in the step that ports the code it governs.

Open questions are at the end.

---

## Package and scope

**D-01. The package is named `leodragkit`, imported as `import leodragkit as ldk`.** User, 2026-10-27. The PyPI, import and repository names are identical, with no separator: PyPI treats `leo-dragkit` and `leodragkit` as different names. On 2026-10-27 the name was free on PyPI, conda-forge and GitHub. Rejected: `dragkit` (searches collide with UI drag-and-drop libraries), `satdrag` (an existing satellite-drag project of that name), `orbitdrag` (accurate but generic).

**D-02. Spacecraft aerodynamics (plate models) are in scope as `leodragkit.aero`.** User, 2026-10-27. With it the package covers both sides of drag: the atmosphere (density) and the spacecraft (Cd·A/m). A physical Cd·A(t) from panel geometry, attitude and the atmosphere state gives an estimate of B that does not come from a density model. contigo_edr uses it for effective density. Method: `Drag_coefficient_primer_for_contigo.md`.

## Structure and dependencies

**D-03. Subpackages are organised by capability, one level deep, with a fixed import order.** User, 2026-10-27. The subpackages are `io`, `density`, `aero`, `orbit`, `forecast` and `workflows`, plus the modules `config`, `cli` and `provenance`. Rejected: grouping by workflow, because `io` and `density` serve every workflow and would have to be duplicated or imported across workflow folders.

**D-04. `aero` imports only numpy and scipy, and nothing from leodragkit.** User, 2026-10-27. contigo and other programs can then use it without starting the JVM or loading density models. Atmosphere inputs reach it as arrays.

**D-05. All Orekit (JPype) code lives in `leodragkit.orbit`.** User, 2026-10-27. Density models and `aero` stay free of Orekit types, so they can be tested and plotted without the JVM.

**D-06. One install with no optional extras; orekit_jpype is a core dependency.** User, 2026-10-27. contigo already uses Orekit, so extras would add complexity for no gain. D-04 keeps `aero` light by an import rule instead of by packaging.

**D-07. `requests` and `pyarrow` are added to the approved dependencies.** User, 2026-10-27. `requests` keeps downloads, including the Space-Track login, easy to read. `pyarrow` is needed for parquet.

**D-08. Caches and saved tables use parquet, not HDF5.** User, 2026-10-27. In the swift_reentry environment, PyTables and h5py could not both load in one process (swift_reentry CLAUDE.md, "OH_sur rules").

**D-09. The machine-learned models from swift_reentry (`ml_r3`, `ml_lag01`) are not ported.** User, 2026-10-27. Their grid cache and below-250 km extension are dropped with them, and xgboost is not a leodragkit dependency. Density models other than MSIS come from the separate model package (D-11).

## Density models

**D-10. A density model is anything that satisfies the `DensityModel` Protocol in `leodragkit/density/interface.py`.** User, 2026-10-27. The Protocol has three parts:

- `density(times_utc, latitude_deg, longitude_deg, altitude_km)` returns density in kg/m³. Solar geometry and local solar time are computed inside it from sim time.
- `f107_features(f107_table)` builds the model's F10.7 features from a daily F10.7 series, usually by wrapping the model's own function. Its column names match the model's cached features.
- The F10.7 window the model needs (lead-in and lead-out days) is declared, so an ensemble can check that the series is long enough. Centred averages, such as MSIS's 81-day mean, need future values.

Models that provide temperature and species number densities also return an `AtmosphereState` dataclass. Model types map to builder functions in a plain dictionary. Rejected: swift_reentry's `@register` decorator, which hides control flow and imports every model's dependencies when the package is imported.

**D-11. The models developed in den_pcaxg move to a separate model package (name open, Q-02) that does its own I/O.** User, 2026-10-27. It takes the models out of research code and lets other programs use them. Its design:

- **Space-weather I/O.** It owns all space-weather I/O (F10.7, Dst, Kp/ap, the NOAA forecast), and leodragkit imports its loaders. This keeps one parser per source.
- **Feature cache.** It keeps a parquet feature cache over all times with drivers. The cache is extended on request from its last row, computing over a lead-in window for lagged and averaged features.
- **Source flags.** Every row carries a source flag per driver, for example `dst_source` (final, provisional or real-time). Rows built from non-final drivers are recomputed when newer data arrive.
- **No extrapolation.** A request past the end of the drivers raises an error that names the last available date.

Its models satisfy D-10 by structure, without importing leodragkit.

**D-12. When `aero` takes temperature and composition from a model other than the density model, it warns and records both.** User, 2026-10-27. The composition model is an explicit config key. If it differs from the density model (in practice, any density model other than MSIS), `aero` raises a `MixedAtmosphereModelWarning`, and its output names both models. No silent fallback (CLAUDE.md, fail fast).

## I/O and provenance

**D-13. `leodragkit.io` holds orbit data only: TLEs, SP3 and attitude.** User, 2026-10-27. Every source module has the same four functions: `local_path_for_<source>`, `download_<source>` (fetches only when the remote copy is newer), `read_<source>_file` (a pure parser) and `load_<source>`. The download-if-newer check lives once, in `io/http_download.py`. Files keep the provider's names so files fetched by other tools can be reused. Forecast files are kept as dated snapshots, never overwritten. Data and output roots come from a main config outside the repository. dataio is not a dependency.

**D-14. There is no CCMC ephemeris reader. Start states come from a state vector with a required frame name.** User, 2026-10-27. The CCMC reader served one Swift task. The function takes the epoch, position, velocity and frame name, with no default frame, because GCRF, ITRF and TEME vectors look alike. It ports `swift_reentry/state.py::state_from_cartesian` and `::check_cartesian_state`. An SP3 start state is a to-do.

**D-15. Every input file is recorded when it is loaded: path, size, modification time and SHA-256.** User, 2026-10-27. Result objects carry the records of all their inputs and write them to the run manifest when saved. Recording at load time rather than at save time means a notebook result saved later still names the inputs it actually used. Several inputs change in place, and a file's modification time alone does not prove its content. Rejected: no records; records without a hash.

**D-30. Space-Track credentials are typed at a prompt (`getpass`), asked once before a download, used to log in and then discarded.** User, 2026-10-27. Typing keeps the credentials out of files and the environment for interactive use. Other secure sources, such as environment variables for runs on GitHub, are added later by decision. Credentials never appear in the repository, configs, logs, manifests or error messages.

## Workflows and outputs

**D-16. Code is organised in three layers: building blocks, workflows and a command line.** User, 2026-10-27.

- **Building blocks** are functions in `io`, `density`, `aero` and `orbit` that return in-memory results.
- **Workflows**, in `leodragkit/workflows/`, cover one task each. Each takes typed settings and returns a result object, writing files only when given an output folder. Each result type has a `save_*` and a `load_*` in the module that produces it, so a notebook gets the same object from a fresh computation or a saved run.
- **The command line**, `ldk <workflow>` in `cli.py`, takes simple flags or a config file, calls one workflow and always saves.

Composite workflows such as `reentry_forecast` chain workflows in memory. There is no `scripts/` folder. Rejected: swift_reentry's design of one script per stage, with stages linked by run folders and run ids.

**D-17. Outputs are stored as `<output_root>/<workflow_name>/<run_id>/`.** User, 2026-10-27. The run id is a UTC timestamp plus an identifier, for example `20261027T153000Z_norad28485`. Each run folder has one `manifest.json` with settings, input records (D-15), code version and seeds. A composite run keeps its stages as subfolders inside its own run folder.

**D-18. The ensemble forecast and the B Monte Carlo require an output folder and fail immediately without one.** User, 2026-10-27. They take hours, and writing each task as it finishes is what allows a resume after a crash. They are the only workflows with resume.

**D-19. F10.7 for ensembles and forward forecasts is loaded in the model package and assembled in `leodragkit/forecast/driver_futures.py`.** User, 2026-10-27. The loader returns one daily series with an `f107_source` flag. It is built from OMNI2 adjusted flux converted to observed flux, observed Penticton flux, and dated NOAA 45-day forecast snapshots. Building each member's series (NOAA baseline times historical anomaly, held beyond day 45) is science convention, so it stays in leodragkit. Each model's `f107_features` then turns the series into features.

**D-20. Time-varying B inside Orekit is deferred.** 2026-10-27. Orekit's standard drag model takes a constant Cd·A, and B(t) would need a custom JPype drag adapter with a Python callback at every step. No current workflow needs it: contigo uses Cd·A(t) directly.

**D-21. `aero` returns B(t) as a time series, with an option to average it over one orbit or a chosen window.** User, 2026-10-27. contigo uses B(t) unaveraged: its effective density already weights B by v³ within each window (`contigo_edr edr_efd.py:148-151`), so averaging B first would change its result. The averaging option serves propagation, which takes a constant B while D-20 holds.

**D-22. Ballistic-coefficient estimation offers two modes, chosen in config.** User, 2026-10-27. Supersedes, for satellites with a geometry, the carried-over convention "B is estimated per density model" as a constant.

- **Constant B** (`constant`): one B fitted per density model, as in swift_reentry. This is the only mode for satellites without a geometry.
- **Scaled aero B** (`scaled_aero`): one dimensionless factor k fitted per density model, with B(t) = k · B_aero(t). Here k = 1 means the density model agrees with the physics.

Pure physics (B_aero(t) with no fit) needs no estimation workflow; it is `aero`'s own output, as contigo uses it.

Consequence: fitting `scaled_aero` means propagating with a B that varies in time, which D-20 defers. Until D-20 is revisited, `scaled_aero` propagates with B_aero averaged per orbit (D-21). See Q-06.

## Aero

**D-23. Energy accommodation α and wall temperature T_w are explicit inputs with no code defaults, and both are written to every output.** User, 2026-10-27. α is the dominant uncertainty in Cd. A hidden default would reach results unnoticed (CLAUDE.md, fail fast). The primer's proposed default T_w = 400 K is not adopted as a code default.

**D-24. The reflected-speed constant k is a parameter, ½ (Koppenwallner, ADBSat code) or ⅔ (Cook, Moe), defaulting to ½ and written to every output.** User, 2026-10-27. The default lets results be compared with ADBSat. The two values agree at α = 1 and differ by percent-level amounts as α falls (primer, section "Choices and pitfalls").

**D-25. The relative velocity is the velocity relative to the co-rotating atmosphere, with no winds.** User, 2026-10-27. This matches contigo_edr's Earth-fixed velocity. Winds are added later, by decision, if a workflow needs them.

**D-26. `aero` computes drag only, not lift.** User, 2026-10-27. Lift is perpendicular to the relative velocity, so it does no work in the co-rotating frame and does not enter contigo's energy dissipation rate. Orekit's drag force acts along the relative velocity only, so nothing uses lift yet.

**D-27. Quaternion functions take the scalar position (first or last) and the frame pair as required arguments, with no defaults.** User, 2026-10-27. A wrong convention silently turns ram faces into wake faces. Each new attitude source gets a test that its nadir-pointing axis points down.

**D-28. The aero method follows the drag-coefficient primer.** User, 2026-10-27. The method:

- free-molecular panel method, each panel a Sentman flat plate under diffuse reflection with incomplete accommodation;
- incidence angle cos δ = n̂_outward · v̂_rel;
- most-probable-speed ratio with one mean molecular mass first, and the per-species form later as a sensitivity test;
- Cd·A and B stored, never Cd alone;
- equations written from the published papers, with ADBSat's GPL-3 code used only as a test oracle.

Full list: `.claude/rules/aero.md`.

## Working with Claude Code

**D-31. Four project subagents, run one at a time: `reference-searcher`, `step-implementer`, `step-reviewer` and `citation-checker`.** User, 2026-10-27. The project defines a coding agent itself rather than leaving it to Claude Code's planning, so every step is implemented under the same written rules.

- The implementer runs only on a plan the user has approved, receives it verbatim, stops when anything is unclear (subagents cannot ask the user questions), and never commits.
- The three others are read-only. The reviewer has Bash to run tests, so its read-only status is enforced by its instructions, not by its tool list.
- Each step cycles: plan → approval → implement → review → the main session checks and reports.

Rejected: swift_reentry's parallel implementers in separate worktrees, and its `doc-sync` agent that wrote docs. Both conflict with the slow, one-change-at-a-time pace.

## Licence

**D-32. leodragkit is released under the MIT licence.** User, 2026-10-27. This is compatible with D-28: the aero code is written from the published equations, and ADBSat's GPL-3 code is used only as a test oracle, never copied or translated.

## Documentation

**D-29. A book without a DOI may be cited by a verified ISBN together with its edition.** User, 2026-10-27. Books such as Vallado's *Fundamentals of Astrodynamics and Applications* (the source of the test-only exponential atmosphere) often have no DOI. Table and equation numbers differ between editions, so the edition is part of the citation.

---

## Open questions

**Q-01. How does the convention "drag depends only on B = Cd·A/m; B is estimated per density model" apply when `aero` models B(t)?** Resolved 2026-10-27 by D-21 and D-22.

**Q-02. Name of the separate model package (D-11).** To be settled when that package is designed.

**Q-03. Citation versions.** Parham & Barba was read as arXiv:1312.3691; the published version is doi:10.2514/6.2014-1492. The Doornbos thesis is cited as the 2011 TU Delft thesis; the published version is doi:10.1007/978-3-642-25129-0. Equation and section numbers must be checked against the version cited before either enters code or docs.

**Q-04. The primer's flat-plate and sphere regression values (for example Cd = 2.1591) are derived, not published.** They are unverified here. Reproduce them independently, for example against ADBSat or Bird's sphere formula, before using them as test references.

**Q-05. Which servers report a modification time for the download-if-newer check?** To be determined per source when each source is ported. Space-Track is a query API, so for it "newer" means TLEs with epochs after the newest one cached.

**Q-06. Can Orekit hold a piecewise-constant drag coefficient without a Python callback?** Orekit parameter drivers may support values that change over time spans, which would let `scaled_aero` use a per-orbit B(t) inside one propagation. This is unverified: check it against the installed Orekit 13 jar before the `scaled_aero` mode is built. If it works, D-20 can be revisited cheaply.

**Q-07. Environment-variable credentials for Space-Track in production runs (planned, D-30).** Investigate before implementing:

- whether Space-Track's terms allow automated access from a CI service and from shared or service accounts;
- how GitHub stores secrets and passes them to a job as environment variables, and how it masks them in logs;
- which source wins when both are possible: environment variables or the prompt;
- how a run without a terminal fails when no environment variable is set. It must raise an error at once, never wait on a prompt nobody can answer;
- the variable names.
