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
| 2 | the header (`read_sp3_header`): version, velocity flag, frame name → `"ITRF"` (IGS08, IGb08, IGS14, IGb14, IGS20, ITR08, ITR14, ITR20; others raise; the field is 5 columns wide), time system, satellite ids; opening plain, gzip, bzip2 and xz files (`sp3_text_lines`, standard library, detected from the first bytes) | Claude (done) |
| 3 | `_sp3_epoch(line)` and `_sp3_vector(line)`: the fixed-column parsers, returning `None` for a bad record | user (template in place) |
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

## Component 3: the record parsers (the user's part)

Both are in `io/sp3_files.py`, each with its columns in the docstring and numbered steps. Python slices count from 0, so columns a–b are `line[a - 1:b]`.

| Function | Columns | Returns |
| --- | --- | --- |
| `_sp3_epoch(line)` | 4–7 year, 9–10 month, 12–13 day, 15–16 hour, 18–19 minute, 21–31 seconds | `datetime64[ns]` on the file's scale; raises `ValueError` if a field is missing, not a number, or the date doesn't exist |
| `_sp3_vector(line)` | 2–4 id; 5–18, 19–32, 33–46 x, y, z (km for `P`, dm/s for `V`) | `(id, array of 3)` in file units, or `None` if any field is blank or not a number, all three are 0.000000, or one is 999999.999999 |

**Required reading:**

- the SP3-c specification (https://files.igs.org/pub/data/format/sp3c.txt), "Line Twenty three" (the epoch record), "Line Twenty four" (position) and "Line Twenty six" (velocity), and the notes on bad or absent values after them: 15 min;
- your Spire file's first records: 2 min.

**Tests (component 3):** 14.

- **Epochs:**
  - a Spire epoch line to the nanosecond;
  - fractional seconds;
  - month 13, a missing seconds field and a non-number each raise.
- **Vectors:**
  - Spire `P` and `V` lines (the absent clock rate ignored);
  - an IGS id;
  - all-zero, a blank field, a non-number, a short line and 999999.999999 each give `None`;
  - a single zero coordinate is kept.

At the start: 14 failed (all `NotImplementedError`), 344 passed. Against a scratch implementation kept out of the repository, all 358 pass.

**Traps:**

- **Seconds to nanoseconds.** Use `round(seconds * 1e9)` as an integer `timedelta64`; adding a float would lose the exact second.
- **A short line gives an empty slice,** and `float("")` raises `ValueError`, which should become `None` in `_sp3_vector` but stay an error in `_sp3_epoch`.
- **Only all three zero is bad.** A single 0.000000 coordinate can be real.

## Done when

All four components are pushed. The user's Spire leoOrb file reads into `SatelliteStates`, with `frame_as_written` `IGS08`, 3306 GPS epochs, and |r| of about 6.67 × 10⁶ m. The tests cover each rule, using small SP3 files written by the tests.

## The user's Spire file (component 2)

`spire_nav_L1B_leoOrb_v06_02_2023-12-18T09-51-49_FM134.sp3` (not committed: Spire data), read 2026-11-03, shows the real layout:

- `#cV` (SP3-c, with velocities); coordinate system **IGS08** (not IGS14); time system GPS; satellite id `134`, the flight-module number, as its comment line explains;
- 3306 epochs at 1 s, each with one `P` and one `V` record;
- clocks present in `P`, and 999999.999999 in `V`;
- lines no longer than 60 characters (no standard-deviation fields);
- |r| from 6665 to 6673 km, an altitude of about 290 km, and speeds of 7.78–7.81 km/s.

`read_sp3_header` reads it as version c, IGS08 → ITRF, GPS, satellites (`134`,), 3306 epochs.
