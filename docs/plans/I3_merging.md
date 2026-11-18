# I3: Merging records from several files

**Status: done 2026-11-03.** User guide: `docs/guides/reading_orbit_and_attitude_files.md`.

Step plan for task I3 in `docs/tasks.md`. Added before A4b on 2026-11-03, when the first end-to-end check had only the 11 minutes two single files shared. Written in full by Claude at the user's request, for review (D-87).

## Goal

Join records of one satellite read from several files, so a day of data can be used, whatever the provider. Providers deliver overlapping pieces: Spire processes in 2-hour windows that overlap by an hour (Spire Attitude and Navigation Product Summary, 2021, §1.2.2), so one epoch can appear in two files, with different values.

## Decisions (the user's answers, 2026-11-03; D-87)

1. **Orbits:** where files overlap, each epoch comes from the file in which it lies **furthest from either end** of that file's span, because a Kalman filter's solution is least reliable near the ends of its arc. Ties go to the earlier file in the list.
2. **Attitude:** an **observed** value beats a repeated or default one, since a gap in one file may be observed in another. Between two of the same kind, the earlier file wins.
3. **Differences in overlaps are reported:** positions and velocities, or attitude angles, through `overlap_differences`, and summarised in one `RecordsMergedWarning`. For orbits, this is a free, empirical measure of the provider's consistency.
4. **Attitude files of different versions are not merged** (raise): their flags mean different things.
5. **SP3 files in different ITRF realisations are merged:** all are `"ITRF"`, differing by millimetres, and every name is kept as written.
6. **Files are passed as a list,** not discovered by provider-specific file names: Spire won't be the only source. A notebook may build the list with `glob`.

## What changed

**Provenance for several files** (in `io/records.py`; I1 and I2's types, readers and tests updated):

| Was | Now |
| --- | --- |
| `input_record: InputRecord` | `input_records: tuple[InputRecord, ...]`, every file read, in order |
| `dropped_record_lines: tuple[int, ...]` | `dropped_records: tuple[tuple[str, int], ...]`, as (file name, line number) |
| `frame_as_written: str` (`SatelliteStates`) | `frames_as_written: tuple[str, ...]` |

`source_names(records)` gives the file names for messages ("a.sp3, b.sp3"). One file gives tuples of one.

**`io/merging.py`:**

| Function | Does |
| --- | --- |
| `merge_satellite_states(list)` | one satellite and frame and kernel (or raise); chooses each epoch by rule 1; keeps every file's provenance |
| `merge_attitude_records(list)` | the same satellite, frame, conventions, version and kernel (or raise); chooses each epoch by rule 2 |
| `overlap_differences(list)` | for each pair of records sharing epochs: the count, median and maximum of the position (m) and velocity (m/s) differences, or the attitude angle (deg) between values observed in both |
| `read_sp3_files(paths, kernel, satellite_id=None)`, `read_spire_attitude_files(paths, kernel)` | read each file, then merge |

The choice is made with one sort: by GPS time, then the score (most central, or observed), then the file's place in the list. The first row of each epoch is kept. The merged `Epochs` are carried over row by row, never recomputed.

## Tests

11, in `tests/io/test_merging.py`, on records built by the tests.

**Orbits:** two spans, 0–10 s and 6–20 s, the second shifted 1 m.

- 7 s comes from the first file;
- 9 s comes from the second;
- the tie at 8 s goes to the earlier file, and to the other file when the list is reversed.

Also checked: provenance kept, including both ITRF names; the warning and `overlap_differences` (5 shared epochs, 1 m); files without overlap joined silently and sorted; one file returned as it is; different satellites, or an empty list, raise.

**Attitude:**

- an epoch repeated in one file but observed in the other takes the observed value;
- two observed values keep the first, with the 10° between them reported;
- different versions raise.

**Reading lists:** two small SP3 files and two attitude files, each pair sharing one epoch.

## Checked with the user's files (exploration; not committed)

The user has one arc of each kind, so overlaps were made by cutting each file in two:

- **Orbit:** FM134's SP3 cut into epochs 0–1999 and 1500–3305, the second shifted 0.5 m in x. Merged: all 3306 epochs. Of the 500 shared, the first 250 came from the first piece and the last 250 from the second, switching exactly midway, as rule 1 gives for two overlapping spans. The warning reported a 0.5 m position difference.
- **Attitude:** FM134's attitude file cut into pairs 0–3999 and 3000–7560, with every observed epoch of the overlap marked repeated (flag 1) in the first piece. Merged: 7561 records, with flags and quaternions identical to the original file. Every observed value was recovered from the second piece.

## Notebook

Section 12 now reads every leoOrb and leoAtt file for the satellite in a directory, merges each kind, and continues as before. It ran here both ways (the user's files, and the fallback orbit), with the same results as before (493 shared observed seconds, azimuth −162.4°).
