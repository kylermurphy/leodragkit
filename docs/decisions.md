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

**D-13. `leodragkit.io` holds orbit data only: TLEs, SP3 and attitude.** User, 2026-10-27. Every source module has the same four functions: `local_path_for_<source>`, `download_<source>` (fetches only when the remote copy is newer), `read_<source>_file` (a pure parser) and `load_<source>`. The download-if-newer check lives once, in `io/http_download.py`. Files keep the provider's names so files fetched by other tools can be reused. Forecast files are kept as dated snapshots, never overwritten. Data and output roots come from a main config outside the repository. dataio is not a dependency. *Superseded in part by D-34: one directory per data source instead of one data root.*

**D-14. There is no CCMC ephemeris reader. Start states come from a state vector with a required frame name.** User, 2026-10-27. The CCMC reader served one Swift task. The function takes the epoch, position, velocity and frame name, with no default frame, because GCRF, ITRF and TEME vectors look alike. It ports `swift_reentry/state.py::state_from_cartesian` and `::check_cartesian_state`. An SP3 start state is a to-do.

**D-15. Every input file is recorded when it is loaded: path, size, modification time and SHA-256.** User, 2026-10-27. Result objects carry the records of all their inputs and write them to the run manifest when saved. Recording at load time rather than at save time means a notebook result saved later still names the inputs it actually used. Several inputs change in place, and a file's modification time alone does not prove its content. Rejected: no records; records without a hash.

**D-30. Space-Track credentials are typed at a prompt (`getpass`), asked once before a download, used to log in and then discarded.** User, 2026-10-27. Typing keeps the credentials out of files and the environment for interactive use. Other secure sources, such as environment variables for runs on GitHub, are added later by decision. Credentials never appear in the repository, configs, logs, manifests or error messages.

**D-33. The main config's default location is `~/.leodragkit/main_config.yaml`, the same for a cloned repository and a pip install.** User, 2026-10-27. Every loader also accepts an explicit path. The location is stated in the README. `create_main_config` writes a new file there and never overwrites one. Rejected: a file in the repository for clones and the home folder for pip installs, which needs leodragkit to detect how it was installed and breaks with both installs; a file inside the installed package, which may be read-only and is deleted by an upgrade. This also settles how workflows find the main config, left open in the structure step: no environment variable is needed.

**D-34. The main config gives the output directory and one directory per data source that leodragkit reads itself, so existing data can be reused wherever it lives.** User, 2026-10-27. Supersedes D-13's single data root. Paths must be absolute (`~` is allowed); relative paths are rejected. A missing directory is created on first load with a warning naming it, after every path has been checked, so an invalid config leaves no folders behind. Each source gets its key in the task that first reads it. T-01 adds `geometry`, `tles` and `orekit_data`. Rejected: one data root with fixed subfolders (cannot point at data elsewhere); requiring directories to exist.

**D-35. `orekit_data: null` loads all Orekit data from the orekit-data pip package; a path names the user's own Orekit data folder, which must already exist.** User, 2026-10-27. That folder is never created, because an empty Orekit data folder would only fail later, far from the cause.

**D-36. Space-weather directories also go in leodragkit's main config, and leodragkit passes them to the model package's loaders.** User, 2026-10-27. The user edits one file. The model package still accepts directories directly, for use without leodragkit. The keys are added in task D1, once those loaders exist.

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

**D-24. The reflected-speed constant k is a parameter, ½ (Koppenwallner, ADBSat code) or ⅔ (Cook, Moe), defaulting to ½ and written to every output.** User, 2026-10-27. The default lets results be compared with ADBSat. The two values agree at α = 1 and differ by percent-level amounts as α falls (primer, section "Choices and pitfalls"). *Superseded for DRIA by D-45.*

**D-25. The relative velocity is the velocity relative to the co-rotating atmosphere, with no winds.** User, 2026-10-27. This matches contigo_edr's Earth-fixed velocity. Winds are added later, by decision, if a workflow needs them.

**D-26. `aero` computes drag only, not lift.** User, 2026-10-27. Lift is perpendicular to the relative velocity, so it does no work in the co-rotating frame and does not enter contigo's energy dissipation rate. Orekit's drag force acts along the relative velocity only, so nothing uses lift yet. *Superseded by D-39.*

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

**D-50. A plate's force is q·A·(C_p·(−n̂_outward) + C_τ·t̂), with t̂ the flow direction (−v̂_rel) projected onto the plate and normalised; so its drag is C_d = C_p cos δ + C_τ sin δ. A plate's coefficients are returned together in a frozen dataclass.** User, 2026-10-29. Fixes the sign convention that task A5 uses to build force vectors from panels (D-39). Named fields cannot be swapped by mistake, which a tuple of three arrays would allow.

## Licence

**D-32. leodragkit is released under the MIT licence.** User, 2026-10-27. This is compatible with D-28: the aero code is written from the published equations, and ADBSat's GPL-3 code is used only as a test oracle, never copied or translated.

**D-38. A back-facing panel keeps its small negative drag; panel contributions are never clipped to zero.** User, 2026-10-28. Molecules striking and leaving a rear face push the plate forward. Summed over a sphere, the plate formula matches Bird's sphere drag only with this sign (R-01), and ADBSat's force sum is likewise signed. Corrects the planning version of the primer, which said back faces give non-negative drag.

**D-39. aero returns the force-coefficient vector as its authoritative result, with drag, lift and side force derived from it; moments are returned when panel positions are known, built after drag works.** User, 2026-10-29. Supersedes D-26. The plate's pressure and shear coefficients give the force vector at almost no extra cost, and a full force vector is what attitude and torque studies need. Plan: `docs/aero_plan.md`.

**D-40. Gas-surface models are built in the order Sentman, then DRIA and CLL; Newton and Cook are used only as test limits.** User, 2026-10-29. DRIA is Sentman applied per species and mass-weighted (ADBSat's `coeff_DRIA.m`), so it adds a mixture rule rather than new physics. Schaaf–Chambré, Maxwell and Storch are parked until a use appears.

**D-41. Every geometry becomes one canonical panel set; geometry code is our own numpy code, with trimesh used only as a test oracle.** User, 2026-10-29. There are three ways in:

- YAML component descriptions (plate, box and cylinder primitives with pose, material and a two-sided flag);
- macro-model tables (normal, area, material, optional position);
- STL/OBJ meshes.

Readers live in `leodragkit.io`. A set without positions supports forces only, and its results say so. trimesh (MIT, numpy-only core) would cover readers and primitives, but its ray casting needs extra compiled packages (rtree or Embree), and the shadowing rule is ours to write either way. Rejected: trimesh as a runtime dependency.

**D-42. Satellites are made of named rigid components, each placed at a pose for every epoch before normals and shadowing are computed; poses stay fixed until articulation is built after CHAMP validation.** User, 2026-10-29. Designing this in now avoids a solver that assumes one rigid shape, which would be costly to undo. Per-epoch geometry is needed anyway, because attitude changes every epoch.

**D-43. Coefficient databases, interpolation, performance work (faster shadowing search, Numba or JAX), constellations, multiple reflections, analytic components and winds are parked; aero stays vectorised over epochs and panels so they can be added.** User, 2026-10-29.

**D-44. aero takes the relative-velocity vector for each epoch and never derives a speed from altitude.** User, 2026-10-29. ADBSat's built-in environment assumes a circular orbit with no co-rotation or winds (`toolbox/calc/environment.m`, `vinf = sqrt(mu_E/(R_E + h))`). Ignoring Earth's rotation alone changes the relative speed by up to about 6% and the flow direction by up to about 3.5° (derived). ADBSat comparisons feed both codes the same explicit speed and flow direction.

**D-45. The reflected-speed constant is tied to the model: Sentman defaults to k = 1/2 (ADBSat's convention); DRIA and the Walker accommodation model use k = 2/3, as published.** User, 2026-10-29. Resolves Q-08 and supersedes D-24 for DRIA. Dey et al. (2025a, eq. 2.4) and Pilinski et al. (2010) define the incident kinetic temperature as mV²/(3k_B), and Walker's Langmuir constant for DRIA was fitted in that formulation. The constant used is written to every output.

**D-46. CLL follows Storch (2002): the one-sided flat-plate force of the Schaaf–Chambré solution, with σ_n from Walker et al. (2014, eq. 27), as Dey et al. (2025a) apply it.** User, 2026-10-29. Resolves Q-09.

- **Force vector.** Storch's eq. 3.9 gives the force per unit area as a normal component plus a component along the flow, in terms of σ_n, σ_t, the speed ratio and Γ₁, Γ₂; §3.2.2 gives the flat plate per side. This supplies the force vector (D-39). Its component along the flow reproduces Dey et al.'s eq. 2.7 (derived; to be tested in A10).
- **Fitted variant.** Walker's fitted eq. 28 parameters, which ADBSat applies at every incidence although they were fitted for a plate facing the flow and for a sphere, come later and only for the ADBSat comparison.

**D-47. TU Delft geometry and SPARTA tables are downloaded into the `geometry` data directory and never committed until their licence is confirmed.** User, 2026-10-29. Resolves Q-10 for now. The licence is checked before task A12 starts.

**D-48. Analytic components (closed-form spheres and cylinders inside a satellite) are parked; their closed forms are used as tests.** User, 2026-10-29. Resolves Q-11. Examples are Dey et al. (2025a), eqs. 2.5–2.6 and 2.8–2.9.

## Documentation

**D-37. Code marks the stages of a function with numbered step comments, and gives reasons in plain words; decision ids stay in the docs.** User, 2026-10-28. A function with more than one stage marks each stage with a numbered comment saying what it does and, when not obvious, why (as in `leodragkit/config.py::load_main_config`). Decision ids (`D-NN`) appear in `docs/` and `.claude/` only, never in code, comments, docstrings or tests; `docs/code_tour.md` links modules to their decisions. Supersedes the part of CLAUDE.md principle 10 that had code cite its decision ids. Rejected: decision ids in comments, which the user found harder to read.


**D-29. A book without a DOI may be cited by a verified ISBN together with its edition.** User, 2026-10-27. Books such as Vallado's *Fundamentals of Astrodynamics and Applications* (the source of the test-only exponential atmosphere) often have no DOI. Table and equation numbers differ between editions, so the edition is part of the citation.

**D-49. A technical report with neither a DOI nor an ISBN is cited by author, year, title, issuing organisation, every report number on its cover and its release statement, with a note of where the copy read came from.** User, 2026-10-29. Extends D-29; resolves Q-12. Example: Storch, J. A. (2002), *Aerodynamic disturbances on spacecraft in free-molecular flow*, The Aerospace Corporation, Aerospace Report No. TR-2003(3397)-1, SMC-TR-03-06, 17 October 2002, approved for public release, distribution unlimited; read from a scanned copy uploaded to the project.

**D-51. Each step's working plan lives in `docs/plans/<task id>_<topic>.md`.** User, 2026-10-29. A plan gives the goal, files, required reading, work order, tests, traps and when the step is done, so the reading list and instructions travel with the code rather than staying in a chat. First example: `docs/plans/A1_flat_plate.md`.

---

## Open questions

**Q-01. How does the convention "drag depends only on B = Cd·A/m; B is estimated per density model" apply when `aero` models B(t)?** Resolved 2026-10-27 by D-21 and D-22.

**Q-02. Name of the separate model package (D-11).** To be settled when that package is designed.

**Q-03. Citation versions.** Parham & Barba was read as arXiv:1312.3691; the published version is doi:10.2514/6.2014-1492. The Doornbos thesis is cited as the 2011 TU Delft thesis; the published version is doi:10.1007/978-3-642-25129-0. Equation and section numbers must be checked against the version cited before either enters code or docs. *Partly resolved 2026-10-28:* the arXiv version of Parham & Barba says it was presented at the AIAA conference of doi:10.2514/6.2014-1492, and its eq. 4 (Bird's sphere drag) was checked there; Doornbos is cited by the Springer version, still unread.

**Q-04. The primer's flat-plate and sphere regression values (for example Cd = 2.1591) are derived, not published.** They are unverified here. Reproduce them independently, for example against ADBSat or Bird's sphere formula, before using them as test references. *Partly addressed 2026-10-28 (R-01):* the plate formula integrated over a sphere matches Bird's formula to six decimals; the plate values are reproduced from the same equations only. Task A2 completes it.

**Q-05. Which servers report a modification time for the download-if-newer check?** To be determined per source when each source is ported. Space-Track is a query API, so for it "newer" means TLEs with epochs after the newest one cached.

**Q-06. Can Orekit hold a piecewise-constant drag coefficient without a Python callback?** Orekit parameter drivers may support values that change over time spans, which would let `scaled_aero` use a per-orbit B(t) inside one propagation. This is unverified: check it against the installed Orekit 13 jar before the `scaled_aero` mode is built. If it works, D-20 can be revisited cheaply.

**Q-07. Environment-variable credentials for Space-Track in production runs (planned, D-30).** Investigate before implementing:

- whether Space-Track's terms allow automated access from a CI service and from shared or service accounts;
- how GitHub stores secrets and passes them to a job as environment variables, and how it masks them in logs;
- which source wins when both are possible: environment variables or the prompt;
- how a run without a terminal fails when no environment variable is set. It must raise an error at once, never wait on a prompt nobody can answer;
- the variable names.

**Q-08. Which reflected-speed constant does each model use?** D-24 made k = 1/2 the default (ADBSat's code). But DRIA as published uses T_k,i = mV²/(3k_B), i.e. k = 2/3 (Dey et al. 2025a, eq. 2.4; Pilinski et al. 2010), and Walker's Langmuir constant for DRIA was fitted in that formulation. Proposal: Sentman keeps 1/2 by default; DRIA and the Walker model use 2/3, recorded in every output. *Resolved 2026-10-29 by D-45.*

**Q-09. Which CLL formulation, and where does its pressure–shear split come from?** There are two: *Resolved 2026-10-29 by D-46.*

- **Dey et al. (2025a, eq. 2.7)**: the Schaaf–Chambré flat plate as derived by Storch (2002), valid at any incidence, with σ_n from Walker's eq. 27.
- **ADBSat's `coeff_CLL.m`**: Walker's fitted eq. 28 parameters, which were fitted for a plate facing the flow and for a sphere, applied at every incidence.

Proposal: Dey/Storch as the baseline, the fitted form later for the ADBSat comparison. Eq. 2.7 gives drag only. The force vector (D-39) needs the separate pressure and shear terms, from Storch (2002) or Schaaf & Chambré (1958), neither of which is available here yet.

**Q-10. What licence covers TU Delft's CHAMP, GRACE, GOCE and Swarm geometry and SPARTA tables?** The standalone plan states CC BY-NC-SA 4.0; this was not confirmed. If true, the files are downloaded into the `geometry` data directory and never committed. *Resolved 2026-10-29 by D-47 (licence still to be checked before A12).*

**Q-11. Should analytic components (closed-form spheres and cylinders, as Dey et al. use for booms) be supported?** Proposal: parked (D-43); their closed forms serve as tests in the meantime.
 *Resolved 2026-10-29 by D-48.*

**Q-12. How are technical reports without a DOI or ISBN cited?** Storch (2002), an Aerospace Corporation report, has neither, so D-29's rule does not cover it. Proposal: cite such reports by author, year, title, issuing organisation, every report number on the cover, and the release statement, and record where the copy read came from. For Storch: The Aerospace Corporation, Aerospace Report No. TR-2003(3397)-1, SMC-TR-03-06, 17 October 2002, approved for public release, distribution unlimited; a scanned copy (uploaded to the project) was read. *Resolved 2026-10-29 by D-49.*
