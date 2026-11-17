"""Tests for SP3 files (task I1): header and opening (component 2), parsing (3), the whole reader (4).

The headers are written by the tests, laid out as in the SP3-c specification and as in Spire's leoOrb files
(3-digit flight-module ids, IGS08, GPS time); Spire's own files are not committed.

Run: ``pytest tests/io/test_sp3_files.py``
"""

import bz2
import gzip
import lzma
import warnings

import numpy as np
import pytest

from leodragkit.io.sp3_files import (
    Sp3RecordsDroppedWarning,
    _sp3_epoch,
    _sp3_vector,
    read_sp3_file,
    read_sp3_header,
    sp3_text_lines,
)

SPIRE_LIKE_HEADER = [
    "#cV2023 12 18 09 52 13.00000000    3306     d IGS08 FIT SPIR",
    "## 2293 121933.00000000     1.00000000 60296 0.4112615738995",
    "+    1   134  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0",
    "+          0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0",
    "++         0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0",
    "%c G  cc GPS ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
    "%c cc cc ccc ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc",
    "%f  0.0000000  0.000000000  0.00000000000  0.000000000000000",
    "%i    0    0    0    0      0      0      0      0         0",
    "/* NOTE: Spire sp3c satellite names are denoted by a",
    "*  2023 12 18  9 52 13.00000000",
    "P134   6631.941824    281.807651   -657.598319  -4211.294181",
    "V134  -6872.336763 -15088.591935 -76310.524044 999999.999999",
    "EOF",
]


def changed(line_number, new_line, header=SPIRE_LIKE_HEADER):
    """A copy of the header with one line replaced."""
    lines = list(header)
    lines[line_number] = new_line
    return lines


def test_a_spire_like_header_is_read():
    header = read_sp3_header(SPIRE_LIKE_HEADER, "FM134.sp3")
    assert (header.version, header.coordinate_system, header.frame) == ("c", "IGS08", "ITRF")
    assert header.time_system == "GPS" and header.satellite_ids == ("134",) and header.epoch_count == 3306


def test_an_igs_header_with_several_satellites_lists_them_all():
    lines = changed(2, "+    3   G01G02G05  0  0  0  0  0  0  0  0  0  0  0  0  0  0")
    assert read_sp3_header(lines, "igs.sp3").satellite_ids == ("G01", "G02", "G05")


@pytest.mark.parametrize("name", ["IGb08", "IGS14", "IGb14", "IGS20", "ITR08", "ITR14", "ITR20"])
def test_every_itrf_realisation_on_the_list_maps_to_itrf(name):
    header = read_sp3_header(changed(0, SPIRE_LIKE_HEADER[0].replace("IGS08", name)), "f.sp3")
    assert (header.coordinate_system, header.frame) == (name, "ITRF")


@pytest.mark.parametrize(
    ("line_number", "new_line", "message"),
    [
        (0, "#aV2023 12 18 09 52 13.00000000    3306     d IGS08 FIT SPIR", "SP3 version 'a'"),
        (0, "#cP2023 12 18 09 52 13.00000000    3306     d IGS08 FIT SPIR", "no velocities"),
        (0, "#cV2023 12 18 09 52 13.00000000    3306     d ITR97 FIT SPIR", "'ITR97' is not on the list"),
        (5, "%c G  cc TAI ccc cccc cccc cccc cccc ccccc ccccc ccccc ccccc", "time system 'TAI'"),
        (
            2,
            "+    2   134  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0",
            "announces 2 satellites but lists 1",
        ),
        (0, "not an sp3 file", "not an SP3 file"),
    ],
    ids=["version a", "positions only", "unknown frame", "TAI", "missing ids", "not SP3"],
)
def test_a_header_that_cannot_be_used_raises_naming_why(line_number, new_line, message):
    with pytest.raises(ValueError, match=message):
        read_sp3_header(changed(line_number, new_line), "f.sp3")


@pytest.mark.parametrize(
    ("suffix", "compress"),
    [("", lambda data: data), (".gz", gzip.compress), (".bz2", bz2.compress), (".xz", lzma.compress)],
    ids=["plain", "gzip", "bzip2", "xz"],
)
def test_plain_and_compressed_files_give_the_same_lines(tmp_path, suffix, compress):
    path = tmp_path / f"orbit.sp3{suffix}"
    path.write_bytes(compress(("\r\n".join(SPIRE_LIKE_HEADER) + "\r\n").encode("ascii")))
    assert list(sp3_text_lines(path)) == SPIRE_LIKE_HEADER  # line endings removed, Windows ones too


@pytest.mark.parametrize(("start", "kind"), [(b"\x1f\x9d", "Unix compress"), (b"PK\x03\x04", "zip")])
def test_unix_compress_and_zip_raise(tmp_path, start, kind):
    path = tmp_path / "orbit.sp3.Z"
    path.write_bytes(start + b"rest of the file")
    with pytest.raises(ValueError, match=kind):
        list(sp3_text_lines(path))


def test_a_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        list(sp3_text_lines(tmp_path / "absent.sp3"))


# --- _sp3_epoch and _sp3_vector (component 3) ----------------------------------------------------


def test_an_epoch_line_gives_its_time_to_the_nanosecond():
    assert _sp3_epoch("*  2023 12 18  9 52 13.00000000") == np.datetime64("2023-12-18T09:52:13", "ns")


def test_fractional_seconds_are_kept():
    assert _sp3_epoch("*  2023 12 18 23 59 59.50000000") == np.datetime64("2023-12-18T23:59:59.5", "ns")


@pytest.mark.parametrize(
    "line",
    [
        "*  2023 13 18  9 52 13.00000000",
        "*  2023 12 18  9 52",
        "*  20x3 12 18  9 52 13.00000000",
        "*  2016 12 31 23 59 60.00000000",
    ],
    ids=["month 13", "no seconds", "not a number", "a leap second (60 s)"],
)
def test_a_malformed_epoch_line_raises(line):
    with pytest.raises(ValueError):
        _sp3_epoch(line)


def test_a_spire_position_line_gives_its_id_and_kilometres():
    satellite_id, values = _sp3_vector("P134   6631.941824    281.807651   -657.598319  -4211.294181")
    assert satellite_id == "134"
    np.testing.assert_array_equal(values, [6631.941824, 281.807651, -657.598319])


def test_a_velocity_line_ignores_the_absent_clock_rate():
    satellite_id, values = _sp3_vector("V134  -6872.336763 -15088.591935 -76310.524044 999999.999999")
    assert satellite_id == "134"
    np.testing.assert_array_equal(values, [-6872.336763, -15088.591935, -76310.524044])


def test_an_igs_style_id_is_read():
    assert _sp3_vector("PG01 -11044.805800 -10475.672350  21929.418200    189.163300")[0] == "G01"


@pytest.mark.parametrize(
    "line",
    [
        "P134      0.000000      0.000000      0.000000  -4211.294181",
        "P134   6631.941824                 -657.598319  -4211.294181",
        "P134   6631.941824    281.8x7651   -657.598319  -4211.294181",
        "P134   6631.941824    281.807651",
        "P134 999999.999999    281.807651   -657.598319  -4211.294181",
        "P134           nan    281.807651   -657.598319  -4211.294181",
        "P134999999.9999990    281.807651   -657.598319  -4211.294181",
    ],
    ids=[
        "all zero",
        "blank field",
        "not a number",
        "cut short",
        "absent value",
        "nan",
        "absent, written longer",
    ],
)
def test_a_bad_record_gives_none(line):
    assert _sp3_vector(line) is None


def test_one_zero_component_is_not_bad():
    # Only all three at 0.000000 means "bad or absent"; one zero coordinate is a real position.
    assert _sp3_vector("P134   6631.941824      0.000000   -657.598319  -4211.294181") is not None


# --- read_sp3_file (component 4) ----------------------------------------------------------------

HEADER_LINES = SPIRE_LIKE_HEADER[:10]


def record(satellite, kind, x, y, z):
    """One P or V line, its three values right-aligned in 14-column fields as the specification has them."""
    return f"{kind}{satellite}{x:>14}{y:>14}{z:>14}{'999999.999999':>14}"


def epoch_line(seconds):
    return f"*  2023 12 18  9 52 {seconds:11.8f}"


GOOD = {
    13: (("6631.941824", "281.807651", "-657.598319"), ("-6872.336763", "-15088.591935", "-76310.524044")),
    14: (("6631.250038", "280.298654", "-665.228927"), ("-6963.373730", "-15091.348514", "-76301.601606")),
    15: (("6630.549149", "278.789383", "-672.858636"), ("-7054.401395", "-15094.071583", "-76292.576286")),
}


def body(seconds=(13, 14, 15), satellite="134"):
    """Epoch, P and V lines for the given seconds, from GOOD."""
    lines = []
    for second in seconds:
        position, velocity = GOOD[second]
        lines += [epoch_line(second), record(satellite, "P", *position), record(satellite, "V", *velocity)]
    return lines


def write_sp3(tmp_path, data_lines, header=HEADER_LINES):
    path = tmp_path / "orbit.sp3"
    path.write_bytes(("\n".join([*header, *data_lines, "EOF"]) + "\n").encode("ascii"))
    return path


def read_quietly(path, kernel, **options):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Sp3RecordsDroppedWarning)  # a clean file must not warn
        return read_sp3_file(path, kernel, **options)


def test_a_clean_file_reads_into_metres_on_epochs(tmp_path, leap_second_kernel):
    states = read_quietly(write_sp3(tmp_path, body()), leap_second_kernel)
    assert len(states) == 3 and states.satellite_id == "134" and states.dropped_record_lines == ()
    assert (states.frame, states.frame_as_written) == ("ITRF", "IGS08")
    np.testing.assert_allclose(states.positions_m[0], [6631941.824, 281807.651, -657598.319])
    np.testing.assert_allclose(states.velocities_m_per_s[0], [-687.2336763, -1508.8591935, -7631.0524044])
    assert states.epochs.gps[0] == np.datetime64("2023-12-18T09:52:13", "ns")
    assert states.epochs.utc[0] == np.datetime64("2023-12-18T09:51:55", "ns")  # GPS − 18 s
    assert states.input_record.path.name == "orbit.sp3"


def test_a_bad_position_drops_its_pair_and_warns_with_the_lines(tmp_path, leap_second_kernel):
    lines = body()
    lines[4] = record("134", "P", "0.000000", "0.000000", "0.000000")  # the second epoch's P (file line 15)
    with pytest.warns(Sp3RecordsDroppedWarning, match="2 record lines .* lines 15, 16"):
        states = read_sp3_file(write_sp3(tmp_path, lines), leap_second_kernel)
    assert len(states) == 2 and states.dropped_record_lines == (15, 16)


def test_a_bad_velocity_drops_its_pair(tmp_path, leap_second_kernel):
    lines = body()
    lines[5] = record("134", "V", "nan", "1.0", "1.0")
    with pytest.warns(Sp3RecordsDroppedWarning):
        assert len(read_sp3_file(write_sp3(tmp_path, lines), leap_second_kernel)) == 2


def test_a_position_without_its_velocity_is_dropped(tmp_path, leap_second_kernel):
    lines = body()
    del lines[5]  # the second epoch's V
    with pytest.warns(Sp3RecordsDroppedWarning):
        states = read_sp3_file(write_sp3(tmp_path, lines), leap_second_kernel)
    assert len(states) == 2 and states.dropped_record_lines == (15,)


def test_a_velocity_without_a_position_is_dropped(tmp_path, leap_second_kernel):
    lines = body()
    del lines[4]  # the second epoch's P
    with pytest.warns(Sp3RecordsDroppedWarning):
        assert read_sp3_file(write_sp3(tmp_path, lines), leap_second_kernel).dropped_record_lines == (15,)


def test_a_repeated_epoch_keeps_the_first(tmp_path, leap_second_kernel):
    lines = body() + body(seconds=(14,))
    with pytest.warns(Sp3RecordsDroppedWarning):
        states = read_sp3_file(write_sp3(tmp_path, lines), leap_second_kernel)
    assert len(states) == 3 and states.dropped_record_lines == (21, 22)


def test_epochs_out_of_order_are_sorted(tmp_path, leap_second_kernel):
    states = read_quietly(write_sp3(tmp_path, body(seconds=(15, 13, 14))), leap_second_kernel)
    assert np.all(np.diff(states.epochs.gps) > np.timedelta64(0, "ns"))
    np.testing.assert_allclose(states.positions_m[0], [6631941.824, 281807.651, -657598.319])


def test_a_file_with_several_satellites_needs_one_chosen(tmp_path, leap_second_kernel):
    header = list(HEADER_LINES)
    header[2] = "+    2   134135  0  0  0  0  0  0  0  0  0  0  0  0  0  0  0"
    lines = []
    for second in (13, 14):
        position, velocity = GOOD[second]
        lines += [epoch_line(second), record("134", "P", *position), record("134", "V", *velocity)]
        lines += [record("135", "P", *position), record("135", "V", *velocity)]
    path = write_sp3(tmp_path, lines, header)
    with pytest.raises(ValueError, match="holds 2 satellites.*\\['134', '135'\\]"):
        read_sp3_file(path, leap_second_kernel)
    with pytest.raises(ValueError, match="no satellite '999'"):
        read_sp3_file(path, leap_second_kernel, satellite_id="999")
    assert len(read_quietly(path, leap_second_kernel, satellite_id="135")) == 2


def test_a_utc_file_uses_utc_epochs(tmp_path, leap_second_kernel):
    header = list(HEADER_LINES)
    header[5] = header[5].replace(" GPS ", " UTC ")
    states = read_quietly(write_sp3(tmp_path, body(), header), leap_second_kernel)
    assert states.epochs.utc[0] == np.datetime64("2023-12-18T09:52:13", "ns")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda lines: lines.__setitem__(3, "*  2023 12 18  9 52 1x.00000000"), "line 14: a malformed epoch"),
        (lambda lines: lines.__setitem__(slice(0, 1), []), "line 11: a record before the first epoch"),
        (lambda lines: lines.__setitem__(slice(None), [epoch_line(13)]), "no good position and velocity"),
    ],
    ids=["malformed epoch", "record before an epoch", "nothing good"],
)
def test_a_file_that_cannot_be_read_raises_naming_the_line(tmp_path, leap_second_kernel, change, message):
    lines = body()
    change(lines)
    with pytest.raises(ValueError, match=message):
        read_sp3_file(write_sp3(tmp_path, lines), leap_second_kernel)
