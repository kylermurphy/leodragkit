# I1: Satellite states from SP3 files

Step plan for task I1 in `docs/tasks.md`; part of the A4 group (`docs/plans/A4_attitude_and_flow_overview.md`). Four components, one patch each, reviewed and pushed before the next.

## Goal

Read SP3 orbit files (Spire's leoOrb, the precise orbit; or podObs, the coarse onboard solution; and IGS files) into `SatelliteStates`: one satellite's positions and velocities in metres, on `Epochs` (UTC, GPS, ET), with the frame from the header mapped to `"ITRF"` (D-79, D-83).

## The format (SP3-c, from the IGS specification)

Source: Hilla, S., *The Extended Standard Product 3 Orbit Format (SP3-c)*, National Geodetic Survey, NOAA, updated 17 August 2010, https://files.igs.org/pub/data/format/sp3c.txt (read 2026-11-03). SP3-d keeps the same layout for everything read here.

| Line | Columns | Holds |
| --- | --- | --- |
| 1 | 1–2 | version: `#c` or `#d` (a and b raise) |
| 1 | 3 | `P` (positions only) or `V` (positions and velocities); `P` raises, since velocity is required |
| 1 | 47–51 | coordinate system, e.g. `IGS14` |
| first `%c` | 10–12 | time system: `GPS` or `UTC` (anything else raises, for now) |
| `*` | 4–31 | an epoch: year, month, day, hour, minute, seconds |
| `P` | 2–4, 5–18, 19–32, 33–46 | satellite id; x, y, z in km |
| `V` | 2–4, 5–18, 19–32, 33–46 | satellite id; vx, vy, vz in dm/s |
| `EOF` | 1–3 | end of data |

**Bad or absent values:** a position or velocity of 0.000000 marks it bad. A clock of 999999.999999 means absent, but leodragkit doesn't read clocks, so it is never a reason to drop a record (D-84).

## Components

| # | Builds | Who |
| --- | --- | --- |
| 1 | `SatelliteStates` in `io/records.py`, with its checks; this plan | Claude |
| 2 | the header: version, velocity flag, frame name → `"ITRF"` (IGS08, IGb08, IGS14, IGb14, IGS20, ITRF2008, ITRF2014, ITRF2020; others raise), time system; opening plain, gzip, bzip2 and xz files (standard library, detected from the first bytes) | Claude |
| 3 | `_sp3_epoch(line)` and `_sp3_vector(line)`: the fixed-column parsers, returning `None` for a bad record | user |
| 4 | `read_sp3_file(path, kernel, satellite_id=None)`: each `P` paired with the `V` after it; bad pairs, unmatched positions and repeated (satellite, epoch) records dropped and their line numbers kept; one warning with the counts | Claude, porting contigo_edr's `df_sp3` rules (without pandas) |

## Decisions in this step

- **One satellite per call.** `satellite_id` is required when the file holds more than one; the error lists the ids. Spire's files hold one.
- **Time systems:** GPS and UTC, through `epochs_from_gps` and `epochs_from_utc`; others raise until a file needs them.
- **Compression:** gzip, bzip2 and xz, with the standard library. Unix `.Z` and zip raise.
- **Versions:** SP3-c and SP3-d.
- **Bad records** (contigo's rules):
  - a bad `P` or `V` (zero, blank or unparsable) drops its pair;
  - a `P` without its `V` is dropped;
  - for a repeated (satellite, epoch), the first good one is kept.

  Every dropped line number is kept in `SatelliteStates.dropped_record_lines`, and one warning summarises them.

## Component 1: `SatelliteStates`

| Field | Holds |
| --- | --- |
| `epochs` | `Epochs`: UTC, GPS, ET |
| `positions_m`, `velocities_m_per_s` | (N, 3) in the frame |
| `frame` | a label from `STATE_FRAMES` (`"ITRF"`) |
| `frame_as_written` | the file's own name, e.g. `IGS14` |
| `satellite_id` | e.g. `L48` |
| `dropped_record_lines` | line numbers of dropped records |
| `input_record` | path, size, time, SHA-256 (D-15) |

Checked whenever created:

- at least one epoch, strictly increasing;
- arrays (N, 3) and finite;
- the frame from the list;
- non-empty ids;
- integer line numbers;
- an `InputRecord`.

**Tests (component 1):** a valid set; each inconsistent field named; repeated epochs rejected.

## Done when

All four components are pushed. A Spire leoOrb file from the user reads into `SatelliteStates`, with `frame_as_written` `IGS14`, GPS epochs, and positions of about 6.9 × 10⁶ m. The tests cover each rule, using small SP3 files written by the tests.
