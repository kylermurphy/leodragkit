# I2: Attitude records from Spire leoAtt files

Step plan for task I2 in `docs/tasks.md`; part of the A4 group (`docs/plans/A4_attitude_and_flow_overview.md`). Four components, one patch each, reviewed and pushed before the next.

## Goal

Read Spire's Level 1A attitude files (`spire_att_L1A_leoAtt_*.log`) into `AttitudeRecords`: every epoch with its quaternion exactly as written, its quality flag, and the conventions needed to read it (D-83, D-84, D-85). `keep_observed` gives the observed epochs. `io` never interprets the quaternions; aero does, in A4a.

## The format

From Spire's *Attitude and Navigation Product Summary* (2021, §2.1.2) and the user's files:

- **Header:**
  - `%spire version 1.2 …`: the version decides the flag meanings;
  - `+satellite … FM134`;
  - `+data_____ sca`: must be `sca`;
  - `+reference gps`: times are GPS;
  - `+first____` and `+last_____`;
  - `*comment:` lines.
- **Records,** in pairs:
  - `tim yyyy mm dd hh mm ss.sssssss f`: a GPS time, then the flag as the last field;
  - `sca qx qy qz qw`: scalar last, taking body vectors into the orbit level frame (u′ = q u q*), Hamilton.
- **End:** `%eof`.
- **Flags by version:**
  - 1.2: 0 observed, 1 repeated (previous value used), 2 default [0, 0, 0, 1];
  - 1.1: 0 real (observed), 1 default.

  An unknown version, or a flag the version doesn't define, raises.

## Components

| # | Builds | Who |
| --- | --- | --- |
| 1 | `AttitudeRecords` and `keep_observed` in `io/records.py`; `io/repeated_warnings.py` (the warning helper `sp3_files.py` had, now shared by io's readers); this plan | Claude (this patch) |
| 2 | the header (`read_spire_attitude_header`): version → flag meanings, satellite, `sca`, the GPS reference; `io/text_files.py` (plain or compressed text lines, shared with the SP3 reader) | Claude (done) |
| 3 | `_attitude_epoch(tim_line)` → (GPS time, flag) and `_attitude_quaternion(sca_line)` → 4 numbers | user (template in place) |
| 4 | `read_spire_attitude_file(path, kernel)`: `tim` paired with the `sca` after it; drop rules as in SP3 (unmatched, unparsable, non-finite, length not 1 within 10⁻⁶, repeated epochs), lines kept, one warning; `Epochs` from GPS; the conventions attached | Claude |

## Decisions in this step (the user's answers, 2026-11-03)

1. `keep_observed` returns new records with only the observed epochs, and warns (every time) with the counts by meaning. The original is untouched, so both can be saved.
2. Bad records are dropped by the SP3 rules, plus a quaternion length check (1 within 10⁻⁶), with their lines kept and one warning.
3. A flag the file's version doesn't define raises, naming the line.
4. The reader reads one file. Merging overlapping files is a workflow's job.

## Component 1: `AttitudeRecords`

| Field | Holds |
| --- | --- |
| `epochs` | `Epochs`: UTC, GPS, ET |
| `quaternions` | (N, 4), exactly as written |
| `scalar_position`, `algebra`, `direction` | from fixed lists: `first`/`last`; `hamilton`/`jpl`; `body_to_reference`/`reference_to_body` (D-81) |
| `frame` | from `ATTITUDE_FRAMES`: `"ITRF"`, `"orbit_level_spire"` |
| `quality_flags`, `flag_meanings` | integers as written, and every flag the version defines; at least one means `"observed"` |
| `satellite_id`, `file_version` | e.g. `FM134`, `1.2` |
| `dropped_record_lines`, `input_record` | as in `SatelliteStates` |

Checked whenever created:

- at least one epoch, strictly increasing;
- quaternions (N, 4) and finite;
- flags are integers, each one defined;
- the conventions and frame come from their lists;
- non-empty labels;
- integer line numbers;
- an `InputRecord`.

**Tests (component 1):** 16.

- valid records;
- `keep_observed` keeps the flag-0 epochs, names the counts left out, and leaves the original unchanged;
- it is silent when all epochs were observed, and raises when none were;
- version 1.1 meanings;
- ten inconsistent fields, each named;
- repeated epochs.

## Component 2: the header

`read_spire_attitude_header(lines, file_name)` reads up to the first `tim` line:

- **Line 1** must start `%spire`; the word after `version` must be a known version (`1.1` or `1.2`), whose flag meanings come from `SPIRE_ATTITUDE_FLAG_MEANINGS` (a copy, so a caller can't alter the table).
- **`+satellite`** gives the satellite (its last word, e.g. `FM134`).
- **`+data_____`** must be `sca`; **`+reference`** must be `gps`.

`SPIRE_ATTITUDE_CONVENTIONS` holds the conventions every leoAtt file uses (scalar last, Hamilton, body to reference, `"orbit_level_spire"`), for component 4 to attach.

Opening files moved to `io/text_files.py` (`text_lines`), now shared by the SP3 and attitude readers. `sp3_text_lines` remains as a thin wrapper, so nothing that used it changes.

**Tests (component 2):** 8.

- a version 1.2 header, laid out as the user's file, with three meanings;
- a version 1.1 header, as in the summary's Figure 2, with two meanings (1 means default there, not repeated);
- five reasons a header is refused: an unknown version, an SP3 file, no satellite, other data, UTC times;
- the meanings returned are a copy.

The user's file reads as version `1.2`, meanings {0: observed, 1: repeated, 2: default}, satellite `FM134`, with records from line 19.

## Component 3: the record parsers (the user's part)

Both are in `io/spire_attitude_files.py`, with numbered steps. Unlike SP3, the lines are split on spaces, not read by column: the leoAtt layout is not column-defined.

| Function | Reads | Returns |
| --- | --- | --- |
| `_attitude_epoch(line)` | `tim` + year, month, day, hour, minute, seconds, flag (eight fields) | (`datetime64[ns]` GPS time, `int` flag); raises `ValueError` for another first word, a field count other than eight, a non-number, a flag that isn't whole, an impossible date, or seconds outside [0, 60) |
| `_attitude_quaternion(line)` | `sca` + qx, qy, qz, qw (five fields) | the four numbers in order, or `None` for another first word, a field count other than five, a non-number, a non-finite value, or a length differing from 1 by more than `QUATERNION_LENGTH_TOLERANCE` (10⁻⁶) |

The default quaternion [0, 0, 0, 1] is read like any other: whether it is kept is decided by its flag (`keep_observed`), not by the parser. Checking a flag against the file's version is component 4's job.

**Required reading:**

- the I2 plan's "The format";
- `_sp3_epoch` (I1), which builds a time the same way;
- 20 records of the user's file, around 08:11, where observed and repeated alternate.

**Tests (component 3):** 18.

- **`tim` lines:** a time and its flag; fractional seconds; seven malformed lines that raise.
- **`sca` lines:** an `sca` line in order; the default read as-is; six bad lines giving `None`; a quaternion rounded to 10 decimals kept.

At the start: 18 failed (all `NotImplementedError`), 397 passed. Against a scratch implementation kept out of the repository, all 415 pass.

**Traps:**

- **The flag must be a whole number:** `int("1.5")` raises, which is what the test wants; don't convert through `float` first.
- **Seconds** become integer nanoseconds (`round(seconds * 1e9)`), as in `_sp3_epoch`.
- **`str.split()` with no argument** splits on any run of spaces, which these lines need (`18  7 57`).

## The user's file

`spire_att_L1A_leoAtt_v06_01_2023-12-18T07-57-00_FM134.log` (not committed: Spire data), read 2026-11-03 (exploration):

- **Header:** version 1.2, satellite FM134, `sca`, GPS; ends with `%eof`.
- **Records:** 7561 `tim`/`sca` pairs, 07:57:18–10:03:18 GPS, every 1 s, none repeated or out of order.
- **Flags:** observed 6284, repeated 726, default 551.
  - The default epochs are the first 551, before attitude data begins (as the summary describes).
  - The repeated epochs are scattered single seconds, often alternating with observed ones (around 08:11).
- **Quaternion lengths:** 1 to within 6 × 10⁻¹¹.
- **Pointing,** for observed epochs read as Hamilton, body to orbit level frame:
  - body z within 0.8° of nadir (median; at most 2.6°);
  - the yaw sits near 0° (1621 epochs) or near 180° (4567), with about 100 in between, during the changes. So FM134 turns end for end in yaw during these two hours.

  Near 0° and 180°, Hamilton and JPL give the same attitude: the convention (Q-14, D-85) only matters during the transitions.
- **Overlap with the user's SP3 file (FM134):** 09:52:13–10:03:18 GPS, 666 epochs, 493 observed and 173 repeated. That is the data for A4a's first end-to-end check.

## Done when

All four components are pushed, and the user's file reads into 7561 records (6284 after `keep_observed`) with version 1.2, frame `"orbit_level_spire"`, and no record dropped.
