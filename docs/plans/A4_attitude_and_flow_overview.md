# A4: Attitude and the flow on the spacecraft, overview

A4 connects a spacecraft's geometry to the flow: given a `PanelSet`, its attitude over time and the air it moves through, it gives every panel at every epoch what the gas-surface models need (incidence, shear direction, speed ratios). With real Spire data, that first needs time scales, an SP3 reader and an attitude reader, so three short steps come before A4 itself. This overview records what was agreed (D-79 to D-84) and the order; each step gets its own plan in `docs/plans/` (D-51), then one patch per component.

## The steps and their components

| Step | Builds | Components, in order (who writes) |
| --- | --- | --- |
| **T-02** time scales | `Epochs`: the same instants as UTC, GPS and SPICE ET (`leodragkit/time_scales.py`) | 1. `spice_kernels` data directory in the main config, and an `io` downloader for the leap-second kernel (Claude). 2. `Epochs` and its conversions through spiceypy (Claude, with the user reviewing). 3. Tests against fixed values (GPS − UTC = 18 s after 2017; UTC 2000-01-01 12:00:00 is ET 64.184 s) |
| **I1** SP3 states | `read_sp3_file` → `SatelliteStates` (`io/sp3_files.py`, `io/records.py`) | 1. `SatelliteStates` (Claude). 2. Header reading: time system checked, frame name mapped to `"ITRF"` (Claude). 3. `P`/`V` record parsing, km → m and dm/s → m/s, ported from contigo_edr's approach without pandas (user). 4. Bad, duplicate and unmatched records reported (Claude) |
| **I2** Spire attitude | `read_spire_attitude_file` → `AttitudeRecords` (`io/spire_attitude_files.py`) | 1. `AttitudeRecords` and `keep_observed` (Claude). 2. The header, including the version and its flag meanings (Claude). 3. `tim`/`sca` line parsing (user) |
| **A4a** attitude | `Attitude`, the orbit frame, the attitude law, conversion to ITRF (`aero/frames.py`) | 1. `Attitude` and conversion from quaternions with their conventions (Claude). 2. The orbit frame from r and v, and the attitude law (user). 3. `"orbit_level_spire"` → `"ITRF"`; checks of epochs, time scale and frame (Claude) |
| **A4b** flow geometry | `PanelFlowGeometry`; plot level 2 (`aero/frames.py`, `plots/spacecraft.py`) | 1. cos δ and the shear direction t̂ per panel and epoch (user). 2. The flow drawn on the spacecraft, panels coloured by cos δ (Claude) |
| **A4c** flow conditions | `AeroAtmosphere` → `FlowConditions` (`aero/flow_conditions.py`) | 1. The types and checks (Claude). 2. Speed ratios, per species and mean (user) |

Each component is its own patch: the user reviews and pushes it before the next. The user's parts arrive as templates inside the component's patch.

## Frames (D-79)

- **The working frame is ITRF** (Earth-fixed, ECEF). The relative velocity is the ITRF velocity itself, because the atmosphere co-rotates with the Earth (D-25): no transform is needed.
- **The inertial velocity, where an attitude law needs it,** is computed in ITRF axes as v_ITRF + ω_E × r, with ω_E along the ITRF z axis. Neglecting precession, nutation and polar motion changes this by far less than a microradian (an estimate, to be checked in A4a). The value of ω_E is cited when it enters the code (A4a), not before.
- **Frame labels come from a fixed, documented list,** and aero checks that attitude and velocity agree:

| Label | Definition |
| --- | --- |
| `"ITRF"` | the International Terrestrial Reference Frame; SP3 headers naming IGS08, IGb08, IGS14, IGb14, IGS20, ITR08, ITR14 or ITR20 map to it (their differences are millimetres) |
| `"orbit_level_spire"` | Spire's orbit level frame (leoAtt header; the Spire product summary, Appendix A.2): Z = −r/\|r\| (nadir), Y = −(r × v)/\|r × v\|, X = Y × Z, with **v the inertial velocity**, computed in ITRF axes as v_ITRF + ω_E × r (D-85) |

## Time (D-82)

- `Epochs` holds every instant as UTC, GPS and SPICE ET (TDB seconds past J2000), so no one has to remember which scale a number is in.
- Conversions go through **spiceypy** with NAIF's leap-second kernel `naif0012.tls`, kept in the main config's new `spice_kernels` directory and downloaded by an `io` module following the four-function template.
- `aero` never imports `time_scales`; it is given times as plain arrays on one scale, with that scale's name, and only checks that the attitude and velocity epochs are identical.

## No interpolation in aero (D-80)

`aero` is evaluated at epochs where the attitude, the velocity and the atmosphere are **all given**, and checks that their times match. The workflow chooses the epochs (for example, the attitude's own times, with orbit states interpolated to them) and owns any resampling and gap rules. Converting B(t) for the orbit propagator remains Q-06 and D-20.

## Attitude (D-81)

- `Attitude` holds epochs, `body_from_reference` (a scipy `Rotation` of T rotations), the reference-frame label and the source.
- Converting quaternions requires, with no defaults: the scalar position (first or last), the algebra (Hamilton or JPL), and the direction (body-to-reference or reference-to-body). These are the classic silent sign errors.
- **The attitude law** (satellites without attitude data): the orbit frame from r and the inertial velocity, plus which body axis points along the flight direction and which towards nadir, both required (`along_velocity="+x"`, `towards_nadir="+z"`; GRACE's leading satellite, for example, flies with body x against its velocity).

## Records from readers (D-83)

- **One dataclass per kind of record,** in `io/records.py`, returned by every reader of that kind:
  - `SatelliteStates`: epochs, positions in m, velocities in m/s, frame label, source;
  - `AttitudeRecords`: epochs, the quaternions as written, the file's conventions, frame label, a quality flag per epoch, source.
- **Velocity is required** in `SatelliteStates`. A file without velocities raises, because deriving them would mean interpolating, which belongs to the workflow.
- **Readers return every epoch with its flag;** `keep_observed` returns the observed epochs and reports what it dropped, so both can be kept.
- **One reader module per file format,** since formats differ (Spire leoAtt text, SP3, later GRACE Level-1B or CCSDS attitude messages).

## Spire specifics (D-84)

From the Spire Attitude and Navigation Product Summary (2021) and the user's files:

- **leoAtt is CHAMP's format plus a quality flag** at the end of each `tim` line. Its meaning depends on the file's version:
  - version 1.2 (the user's files): 0 observed; 1 missing, previous value repeated; 2 missing, default [0, 0, 0, 1];
  - version 1.1 (the summary's example): 0 real; 1 default.

  The reader reads the version and raises on one it doesn't know.
- **Quaternions:** qx, qy, qz, qw (scalar last). They take a body vector into the orbit level frame (u′ = q u q*), so the direction is body to orbit level. The algebra is **Hamilton** (D-85, by decision: no document states the multiplication rule, and the data cannot decide, because both readings point the body to nadir and differ only in the sign of the yaw).
- **Body frame** (summary, Appendix A.1): +Z along the 3U long axis, away from the zenith-facing POD antenna, so it points to nadir in nominal pointing. The user's sample agrees: body z within 0.5° of nadir, yawed 14.6°.
- **Time:** GPS.
- **SP3 (leoOrb, the precise orbit; podObs, the coarse onboard solution):** a `P` line (km, then a clock offset) and a `V` line (dm/s, then a clock rate, usually 999999.999999 for "not estimated", which is ignored, not treated as a bad record). The frame is in the header: the summary says IGS08, the user's files say IGS14.

## Questions settled during planning

- **Q-14** (Hamilton or JPL for Spire): Hamilton, by the user's decision (D-85).
- **Q-15** (which velocity defines Spire's orbit frame): inertial, on evidence (D-85). Both are recorded so that a different answer from Spire changes one argument in one place.

## References

- Spire Global, Inc. (2021). *Spire Attitude and Navigation Product Summary*, Version 1.0, 2021-09-08. No report number, DOI or ISBN; cited as D-49 requires. Read: the PDF uploaded to the conversation; §2.1.2 (leoAtt), §2.1.3 (telAtt), §2.2.4–2.2.5 (SP3), Appendix A (frames).
- CDAAC (COSMIC Data Analysis and Archive Center), *leoAtt file format* (COSMIC), https://cdaac-www.cosmic.ucar.edu/cdaac/cgi_bin/fileFormats.cgi?type=leoAtt, read 2026-11-02. A web page without version or date beyond "Last Modified: 2026"; evidence for the inertial velocity (Q-15), not for Spire's own conventions.
