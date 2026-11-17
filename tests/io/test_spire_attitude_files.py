"""Tests for Spire attitude files (task I2): the header (2), the record parsers (3), the whole reader (4).

Headers are written by the tests: version 1.2 laid out as the user's leoAtt files, version 1.1 as the example
in Spire's product summary (§2.1.2, Figure 2). Spire's own files are not committed.

Run: ``pytest tests/io/test_spire_attitude_files.py``
"""

import warnings

import numpy as np
import pytest

from leodragkit.io.spire_attitude_files import (
    AttitudeRecordsDroppedWarning,
    _attitude_epoch,
    _attitude_quaternion,
    read_spire_attitude_file,
    read_spire_attitude_header,
)

VERSION_1_2_HEADER = [
    "%spire version 1.2  revision   1 2019 01 29 00:00 Spire     Spire Processing Center",
    "+satellite       0  FM134                ",
    "+data_____ sca",
    "+reference gps",
    "+first____  2023 12 18  7 57 18.0000000 ",
    "+last_____  2023 12 18 10  3 18.0000000 ",
    "*comment:  tim: GPS time: yr, mon, day, hr, min, sec",
    "*comment:  sca: Quaternion to convert spacecraft reference frame to orbit level frame:",
    "*comment:      '0': Valid observed data used",
    "*comment:      '1': Epoch is missing. Previous valid data used",
    "*comment:      '2': Epoch is missing. Default quaterion used",
    "tim 2023 12 18  7 57 18.0000000 2",
    "sca  0.0000000000  0.0000000000  0.0000000000  1.0000000000",
]

VERSION_1_1_HEADER = [
    "%spire version 1.1  revision   1 2018 12 12 00:00 Spire     Spire Processing Center",
    "+satellite       0  FM046",
    "+data_____ sca",
    "+reference gps",
    "+first____  2018  5  3 14  2 41.0000000",
    "+last_____  2018  5  3 14 57 40.0000000",
    "*comment:  Last character of 'tim' field denotes real ('0') or default data ('1').",
    "tim 2018  5  3 14  2 41.0000000 0",
    "sca  0.0078740157  0.0000000000 -0.9921259843  0.0000000000",
]


def changed(header, line_number, new_line):
    lines = list(header)
    lines[line_number] = new_line
    return lines


def test_a_version_1_2_header_gives_its_three_flag_meanings():
    header = read_spire_attitude_header(VERSION_1_2_HEADER, "FM134.log")
    assert (header.file_version, header.satellite_id) == ("1.2", "FM134")
    assert header.flag_meanings == {0: "observed", 1: "repeated", 2: "default"}
    assert header.first_record_line == 12


def test_a_version_1_1_header_gives_its_two_flag_meanings():
    header = read_spire_attitude_header(VERSION_1_1_HEADER, "FM046.log")
    assert (header.file_version, header.satellite_id) == ("1.1", "FM046")
    assert header.flag_meanings == {0: "observed", 1: "default"}  # 1 means default here, not repeated


@pytest.mark.parametrize(
    ("line_number", "new_line", "message"),
    [
        (0, "%spire version 2.0  revision   1 2025 01 01 00:00 Spire", "version '2.0'"),
        (0, "#cV2023 12 18 09 52 13.00000000    3306     d IGS08 FIT SPIR", "not a Spire attitude file"),
        (1, "+satellite", "no '\\+satellite' line"),
        (2, "+data_____ sca2", "must be 'sca'"),
        (3, "+reference utc", "must be 'gps'"),
    ],
    ids=["unknown version", "an SP3 file", "no satellite", "other data", "UTC times"],
)
def test_a_header_that_cannot_be_used_raises_naming_why(line_number, new_line, message):
    with pytest.raises(ValueError, match=message):
        read_spire_attitude_header(changed(VERSION_1_2_HEADER, line_number, new_line), "f.log")


def test_the_flag_meanings_returned_are_a_copy():
    header = read_spire_attitude_header(VERSION_1_2_HEADER, "FM134.log")
    header.flag_meanings[3] = "invented"
    assert 3 not in read_spire_attitude_header(VERSION_1_2_HEADER, "FM134.log").flag_meanings


# --- _attitude_epoch and _attitude_quaternion (component 3) ---------------------------------------


def test_a_tim_line_gives_its_gps_time_and_flag():
    epoch, flag = _attitude_epoch("tim 2023 12 18  7 57 18.0000000 2")
    assert epoch == np.datetime64("2023-12-18T07:57:18", "ns") and flag == 2


def test_fractional_seconds_are_kept_to_the_nanosecond():
    epoch, flag = _attitude_epoch("tim 2023 12 18 10  3 17.2500000 0")
    assert epoch == np.datetime64("2023-12-18T10:03:17.25", "ns") and flag == 0


@pytest.mark.parametrize(
    "line",
    [
        "tim 2023 13 18  7 57 18.0000000 2",
        "tim 2023 12 18  7 57 60.0000000 0",
        "tim 2023 12 18  7 57 18.0000000",
        "tim 2023 12 18  7 57 18.0000000 2 9",
        "tim 2023 12 18  7 57 18.0000000 x",
        "tim 2023 12 18  7 57 18.0000000 1.5",
        "sca 2023 12 18  7 57 18.0000000 2",
    ],
    ids=[
        "month 13",
        "a leap second",
        "no flag",
        "an extra field",
        "flag not a number",
        "flag not whole",
        "not tim",
    ],
)
def test_a_bad_tim_line_raises(line):
    with pytest.raises(ValueError):
        _attitude_epoch(line)


def test_an_sca_line_gives_its_four_numbers_in_order():
    np.testing.assert_array_equal(
        _attitude_quaternion("sca -0.0083316449  0.0036622615  0.9929916885  0.1178332640"),
        [-0.0083316449, 0.0036622615, 0.9929916885, 0.1178332640],
    )


def test_the_default_quaternion_is_read_like_any_other():
    # Whether a default is kept is decided by its flag (keep_observed), not by the parser.
    np.testing.assert_array_equal(
        _attitude_quaternion("sca  0.0000000000  0.0000000000  0.0000000000  1.0000000000"), [0, 0, 0, 1]
    )


@pytest.mark.parametrize(
    "line",
    [
        "sca -0.0083316449  0.0036622615  0.9929916885",
        "sca -0.0083316449  0.0036622615  0.9929916885  0.1178332640  1.0",
        "sca -0.0083316449  0.0036622615  0.99299x6885  0.1178332640",
        "sca          nan  0.0036622615  0.9929916885  0.1178332640",
        "sca  0.0000000000  0.0000000000  0.0000000000  1.1000000000",
        "tim -0.0083316449  0.0036622615  0.9929916885  0.1178332640",
        "",
    ],
    ids=["three numbers", "five numbers", "not a number", "nan", "length 1.1", "not sca", "empty"],
)
def test_a_bad_sca_line_gives_none(line):
    assert _attitude_quaternion(line) is None


def test_a_quaternion_rounded_to_ten_decimals_is_kept():
    # Written to 10 decimals, a unit quaternion's length can miss 1 by about 1e-10: well within the tolerance.
    assert _attitude_quaternion("sca -0.0083316449  0.0036622615  0.9929916885  0.1178332641") is not None


# --- read_spire_attitude_file (component 4) -------------------------------------------------------

HEADER_1_2 = VERSION_1_2_HEADER[:11]
TURNED = "sca -0.0040895075 -0.0001525936 -0.1268052501  0.9919191909"  # about 14.6 deg of yaw
DEFAULT = "sca  0.0000000000  0.0000000000  0.0000000000  1.0000000000"


def tim(second, flag):
    return f"tim 2023 12 18  9 52 {second:10.7f} {flag}"


def records_body(seconds_and_flags=((13, 2), (14, 0), (15, 1), (16, 0))):
    """tim and sca lines; flag 2 gets the default quaternion, others the turned one."""
    lines = []
    for second, flag in seconds_and_flags:
        lines += [tim(second, flag), DEFAULT if flag == 2 else TURNED]
    return lines


def write_attitude(tmp_path, body_lines, header=HEADER_1_2):
    path = tmp_path / "attitude.log"
    path.write_bytes(("\n".join([*header, *body_lines, "%eof"]) + "\n").encode("ascii"))
    return path


def read_quietly(path, kernel):
    with warnings.catch_warnings():
        warnings.simplefilter("error", AttitudeRecordsDroppedWarning)  # a clean file must not warn
        return read_spire_attitude_file(path, kernel)


def test_a_clean_file_reads_every_epoch_with_its_flag_and_conventions(tmp_path, leap_second_kernel):
    records = read_quietly(write_attitude(tmp_path, records_body()), leap_second_kernel)
    assert len(records) == 4 and records.quality_flags.tolist() == [2, 0, 1, 0]
    assert (records.scalar_position, records.algebra, records.direction, records.frame) == (
        "last",
        "hamilton",
        "body_to_reference",
        "orbit_level_spire",
    )
    assert (records.satellite_id, records.file_version, records.dropped_records) == ("FM134", "1.2", ())
    np.testing.assert_array_equal(records.quaternions[0], [0, 0, 0, 1])
    assert records.epochs.utc[0] == np.datetime64("2023-12-18T09:51:55", "ns")  # GPS − 18 s


def test_a_version_1_1_file_reads_with_its_own_flags(tmp_path, leap_second_kernel):
    header = VERSION_1_1_HEADER[:7]
    records = read_quietly(
        write_attitude(tmp_path, records_body(((13, 1), (14, 0))), header), leap_second_kernel
    )
    assert records.flag_meanings == {0: "observed", 1: "default"} and records.quality_flags.tolist() == [1, 0]


def test_a_flag_the_version_does_not_define_raises_naming_the_line(tmp_path, leap_second_kernel):
    with pytest.raises(ValueError, match="line 14: flag 3 is not one that version 1.2 defines"):
        read_spire_attitude_file(
            write_attitude(tmp_path, records_body(((13, 0), (14, 3)))), leap_second_kernel
        )


def test_a_malformed_tim_line_raises_naming_the_line(tmp_path, leap_second_kernel):
    lines = records_body()
    lines[2] = "tim 2023 12 18  9 52 xx.0000000 0"
    with pytest.raises(ValueError, match="line 14: a malformed tim line"):
        read_spire_attitude_file(write_attitude(tmp_path, lines), leap_second_kernel)


def test_a_bad_quaternion_drops_its_pair_and_warns_with_the_lines(tmp_path, leap_second_kernel):
    lines = records_body()
    lines[3] = "sca  0.0000000000  0.0000000000  0.0000000000  1.1000000000"  # the second pair (lines 14, 15)
    with pytest.warns(AttitudeRecordsDroppedWarning, match="2 attitude record lines .* lines 14, 15"):
        records = read_spire_attitude_file(write_attitude(tmp_path, lines), leap_second_kernel)
    assert len(records) == 3 and records.dropped_records == (("attitude.log", 14), ("attitude.log", 15))


def test_unmatched_tim_and_sca_lines_are_dropped(tmp_path, leap_second_kernel):
    lines = records_body()
    del lines[3]  # the second sca: its tim (line 14) is left unmatched
    lines.insert(0, TURNED)  # an sca before any tim (line 12)
    with pytest.warns(AttitudeRecordsDroppedWarning):
        records = read_spire_attitude_file(write_attitude(tmp_path, lines), leap_second_kernel)
    assert len(records) == 3 and records.dropped_records == (("attitude.log", 12), ("attitude.log", 15))


def test_a_repeated_epoch_keeps_the_first_and_epochs_are_sorted(tmp_path, leap_second_kernel):
    lines = records_body(((15, 0), (13, 0), (14, 0), (13, 1)))
    with pytest.warns(AttitudeRecordsDroppedWarning):
        records = read_spire_attitude_file(write_attitude(tmp_path, lines), leap_second_kernel)
    assert len(records) == 3 and records.quality_flags.tolist() == [
        0,
        0,
        0,
    ]  # the later 13 s (flag 1) dropped
    assert np.all(np.diff(records.epochs.gps) > np.timedelta64(0, "ns"))


def test_lines_after_eof_are_not_read(tmp_path, leap_second_kernel):
    path = write_attitude(tmp_path, records_body())
    path.write_bytes(path.read_bytes() + b"anything at all\n")
    assert len(read_quietly(path, leap_second_kernel)) == 4


@pytest.mark.parametrize(
    ("body_lines", "message"),
    [
        (["tim 2023 12 18  9 52 13.0000000 0", "abc 1 2 3 4"], "line 13: expected a tim or sca line"),
        (["tim 2023 12 18  9 52 13.0000000 0"], "no good tim and sca records"),
    ],
    ids=["an unknown line", "nothing good"],
)
def test_a_file_that_cannot_be_read_raises(tmp_path, leap_second_kernel, body_lines, message):
    with pytest.raises(ValueError, match=message):
        read_spire_attitude_file(write_attitude(tmp_path, body_lines), leap_second_kernel)
