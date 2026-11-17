"""Tests for SP3 files (task I1, component 2): the header, and opening plain and compressed files.

The headers are written by the tests, laid out as in the SP3-c specification and as in Spire's leoOrb files
(3-digit flight-module ids, IGS08, GPS time); Spire's own files are not committed.

Run: ``pytest tests/io/test_sp3_files.py``
"""

import bz2
import gzip
import lzma

import pytest

from leodragkit.io.sp3_files import read_sp3_header, sp3_text_lines

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
