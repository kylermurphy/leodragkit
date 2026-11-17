"""Tests for merging records from several files (task I3).

Records are built by the tests. Orbits: two overlapping spans whose positions differ by a known offset, so
the value kept at each overlapping epoch shows which file it came from. Attitude: an epoch repeated in one
file and observed in the other, and two observed values that differ by a known angle.

Run: ``pytest tests/io/test_merging.py``
"""

import warnings

import numpy as np
import pytest

from leodragkit.io.merging import (
    RecordsMergedWarning,
    merge_attitude_records,
    merge_satellite_states,
    overlap_differences,
    read_sp3_files,
    read_spire_attitude_files,
)
from leodragkit.io.records import AttitudeRecords, SatelliteStates, input_record_for
from leodragkit.time_scales import epochs_from_gps

START = np.datetime64("2023-12-18T09:52:00", "ns")


def seconds(first, last):
    return START + (np.arange(first, last + 1) * 1e9).astype("timedelta64[ns]")


def states_over(tmp_path, kernel, first, last, shift_m=0.0, name="a.sp3", satellite="134", written="IGS08"):
    """States at 1 s from `first` to `last` s, x = 6.67e6 m + shift_m; a file stands in as the source."""
    times = seconds(first, last)
    source = tmp_path / name
    source.write_bytes(name.encode())
    along_track_m = np.arange(first, last + 1) * 7.8e3  # by absolute second: files agree where they overlap
    positions = np.column_stack([np.full(len(times), 6.67e6 + shift_m), along_track_m, np.zeros(len(times))])
    return SatelliteStates(
        epochs=epochs_from_gps(times, kernel),
        positions_m=positions,
        velocities_m_per_s=np.tile([0.0, 7.8e3, 0.0], (len(times), 1)),
        frame="ITRF",
        frames_as_written=(written,),
        satellite_id=satellite,
        dropped_records=((name, 99),),
        input_records=(input_record_for(source),),
    )


def merged_quietly(function, items):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RecordsMergedWarning)
        return function(items)


# --- orbits ---------------------------------------------------------------------------------------


def test_each_overlapping_epoch_comes_from_the_file_where_it_is_furthest_from_the_ends(
    tmp_path, leap_second_kernel
):
    # File a spans 0–10 s, file b (shifted 1 m) spans 6–20 s. At 7 s: 3 s from a's end, 1 s from b's start: a.
    # At 9 s: 1 s from a's end, 3 s from b's start: b. At 8 s both are 2 s from an end: the earlier file, a.
    first = states_over(tmp_path, leap_second_kernel, 0, 10, name="a.sp3")
    second = states_over(tmp_path, leap_second_kernel, 6, 20, shift_m=1.0, name="b.sp3")
    merged = merged_quietly(merge_satellite_states, [first, second])
    assert len(merged) == 21
    from_b = merged.positions_m[:, 0] == 6.67e6 + 1.0
    np.testing.assert_array_equal(np.flatnonzero(from_b), np.arange(9, 21))  # 0–8 s from a, 9–20 s from b


def test_the_order_of_the_list_only_breaks_ties(tmp_path, leap_second_kernel):
    first = states_over(tmp_path, leap_second_kernel, 0, 10, name="a.sp3")
    second = states_over(tmp_path, leap_second_kernel, 6, 20, shift_m=1.0, name="b.sp3")
    reversed_order = merged_quietly(merge_satellite_states, [second, first])
    from_b = reversed_order.positions_m[:, 0] == 6.67e6 + 1.0
    np.testing.assert_array_equal(np.flatnonzero(from_b), np.arange(8, 21))  # the tie at 8 s now goes to b


def test_merged_states_keep_every_file_and_dropped_record(tmp_path, leap_second_kernel):
    first = states_over(tmp_path, leap_second_kernel, 0, 10, name="a.sp3")
    second = states_over(tmp_path, leap_second_kernel, 6, 20, name="b.sp3", written="IGS14")
    merged = merged_quietly(merge_satellite_states, [first, second])
    assert [record.path.name for record in merged.input_records] == ["a.sp3", "b.sp3"]
    assert merged.dropped_records == (("a.sp3", 99), ("b.sp3", 99))
    assert merged.frames_as_written == ("IGS08", "IGS14")  # both ITRF realisations, kept as written


def test_overlaps_are_reported_in_one_warning_and_by_overlap_differences(tmp_path, leap_second_kernel):
    first = states_over(tmp_path, leap_second_kernel, 0, 10, name="a.sp3")
    second = states_over(tmp_path, leap_second_kernel, 6, 20, shift_m=1.0, name="b.sp3")
    with pytest.warns(RecordsMergedWarning, match="5 repeated epochs resolved.*position up to 1 m"):
        merge_satellite_states([first, second])
    position, velocity = overlap_differences([first, second])
    assert (position.quantity, position.shared_epochs, position.maximum) == (
        "position",
        5,
        pytest.approx(1.0),
    )
    assert (velocity.quantity, velocity.maximum) == ("velocity", 0.0)


def test_files_that_do_not_overlap_are_joined_without_a_warning(tmp_path, leap_second_kernel):
    first = states_over(tmp_path, leap_second_kernel, 0, 10, name="a.sp3")
    second = states_over(tmp_path, leap_second_kernel, 20, 30, name="b.sp3")
    with warnings.catch_warnings():
        warnings.simplefilter("error", RecordsMergedWarning)
        assert len(merge_satellite_states([second, first])) == 22  # sorted by time, whatever the list order


def test_one_file_is_returned_as_it_is(tmp_path, leap_second_kernel):
    only = states_over(tmp_path, leap_second_kernel, 0, 10)
    assert merge_satellite_states([only]) is only


def test_different_satellites_or_an_empty_list_raise(tmp_path, leap_second_kernel):
    first = states_over(tmp_path, leap_second_kernel, 0, 10, name="a.sp3")
    other = states_over(tmp_path, leap_second_kernel, 6, 20, name="b.sp3", satellite="135")
    with pytest.raises(ValueError, match="different satellite_id"):
        merge_satellite_states([first, other])
    with pytest.raises(ValueError, match="at least one"):
        merge_satellite_states([])


# --- attitude -------------------------------------------------------------------------------------

SPIRE_FLAGS = {0: "observed", 1: "repeated", 2: "default"}
YAW_10_DEG = [0.0, 0.0, np.sin(np.radians(5)), np.cos(np.radians(5))]  # 10° about z, scalar last


def attitude_over(
    tmp_path, kernel, first, last, flags=None, quaternion=(0.0, 0.0, 0.0, 1.0), name="a.log", version="1.2"
):
    times = seconds(first, last)
    source = tmp_path / name
    source.write_bytes(name.encode())
    return AttitudeRecords(
        epochs=epochs_from_gps(times, kernel),
        quaternions=np.tile(quaternion, (len(times), 1)),
        scalar_position="last",
        algebra="hamilton",
        direction="body_to_reference",
        frame="orbit_level_spire",
        quality_flags=np.zeros(len(times), dtype=np.int64) if flags is None else np.array(flags),
        flag_meanings=SPIRE_FLAGS if version == "1.2" else {0: "observed", 1: "default"},
        satellite_id="FM134",
        file_version=version,
        dropped_records=(),
        input_records=(input_record_for(source),),
    )


def test_an_epoch_observed_in_one_file_beats_a_repeated_value_in_another(tmp_path, leap_second_kernel):
    # a: 0–4 s, repeated (flag 1) at 3 and 4 s; b: 3–6 s, all observed, turned 10° (so its values show).
    first = attitude_over(tmp_path, leap_second_kernel, 0, 4, flags=[0, 0, 0, 1, 1], name="a.log")
    second = attitude_over(tmp_path, leap_second_kernel, 3, 6, quaternion=YAW_10_DEG, name="b.log")
    merged = merged_quietly(merge_attitude_records, [first, second])
    assert len(merged) == 7 and merged.quality_flags.tolist() == [0] * 7
    np.testing.assert_allclose(merged.quaternions[3:], [YAW_10_DEG] * 4)


def test_two_observed_values_keep_the_first_and_report_the_angle_between_them(tmp_path, leap_second_kernel):
    first = attitude_over(tmp_path, leap_second_kernel, 0, 4, name="a.log")
    second = attitude_over(tmp_path, leap_second_kernel, 3, 6, quaternion=YAW_10_DEG, name="b.log")
    with pytest.warns(RecordsMergedWarning, match="attitude angle up to 10 deg"):
        merged = merge_attitude_records([first, second])
    np.testing.assert_allclose(merged.quaternions[3:5], [[0, 0, 0, 1]] * 2)  # the first file's values
    (angle,) = overlap_differences([first, second])
    assert (angle.shared_epochs, angle.maximum) == (2, pytest.approx(10.0))


def test_attitude_files_of_different_versions_are_not_merged(tmp_path, leap_second_kernel):
    first = attitude_over(tmp_path, leap_second_kernel, 0, 4, name="a.log")
    older = attitude_over(tmp_path, leap_second_kernel, 3, 6, name="b.log", version="1.1")
    with pytest.raises(ValueError, match="different file_version"):
        merge_attitude_records([first, older])


# --- reading lists of files -----------------------------------------------------------------------


def test_lists_of_files_are_read_and_merged(tmp_path, leap_second_kernel):
    header = [
        "#cV2023 12 18 09 52 13.00000000       2     d IGS08 FIT SPIR",
        "## 2293 121933.00000000     1.00000000 60296 0.4112615738995",
        "+    1   134  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0",
        "%c G  cc GPS ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
    ]

    def sp3_epoch(second):
        return [
            f"*  2023 12 18  9 52 {second:11.8f}",
            "P134   6631.941824    281.807651   -657.598319  -4211.294181",
            "V134  -6872.336763 -15088.591935 -76310.524044 999999.999999",
        ]

    paths = []
    for name, span in (("a.sp3", (13, 14)), ("b.sp3", (14, 15))):
        path = tmp_path / name
        path.write_text(
            "\n".join(header + [line for second in span for line in sp3_epoch(second)] + ["EOF"]) + "\n"
        )
        paths.append(path)
    states = merged_quietly(lambda items: read_sp3_files(items, leap_second_kernel), paths)
    assert len(states) == 3 and [record.path.name for record in states.input_records] == ["a.sp3", "b.sp3"]

    attitude_header = [
        "%spire version 1.2  revision   1 2019 01 29 00:00 Spire     Spire Processing Center",
        "+satellite       0  FM134",
        "+data_____ sca",
        "+reference gps",
    ]
    attitude_paths = []
    for name, span in (("a.log", (13, 14)), ("b.log", (14, 15))):
        path = tmp_path / name
        records = [
            line for second in span for line in (f"tim 2023 12 18  9 52 {second:10.7f} 0", "sca 0 0 0 1")
        ]
        path.write_text("\n".join(attitude_header + records + ["%eof"]) + "\n")
        attitude_paths.append(path)
    records = merged_quietly(
        lambda items: read_spire_attitude_files(items, leap_second_kernel), attitude_paths
    )
    assert len(records) == 3 and records.satellite_id == "FM134"
    with pytest.raises(ValueError, match="at least one path"):
        read_sp3_files([], leap_second_kernel)
