"""Tests for the leap-second kernel module (task T-02, component 1).

Offline tests use a small hand-written kernel, with the pinned SHA-256 replaced by the fake file's own;
one test, marked ``network``, downloads the real naif0012.tls from NAIF.

Run: ``pytest tests/io/test_spice_kernels.py`` (add ``-m network`` for the download).
"""

import hashlib
from datetime import date

import pytest

from leodragkit.io import spice_kernels
from leodragkit.io.spice_kernels import (
    LEAP_SECOND_KERNEL_NAME,
    load_leap_second_kernel,
    local_path_for_leap_second_kernel,
    read_leap_second_kernel_file,
)

FAKE_KERNEL = """KPL/LSK

A small leap-second kernel, in NAIF's format, for tests.

\\begindata

DELTET/DELTA_T_A       =   32.184
DELTET/DELTA_AT        = ( 10,   @1972-JAN-1
                           11,   @1972-JUL-1
                           37,   @2017-JAN-1 )

\\begintext
"""


def write_fake_kernel(directory, text=FAKE_KERNEL, monkeypatch=None):
    """Write the fake kernel under its real name; with monkeypatch, pin its own SHA-256."""
    path = local_path_for_leap_second_kernel(directory)
    path.write_bytes(text.encode("ascii"))  # bytes, so Windows doesn't turn each \n into \r\n
    if monkeypatch is not None:
        monkeypatch.setattr(
            spice_kernels, "LEAP_SECOND_KERNEL_SHA256", hashlib.sha256(path.read_bytes()).hexdigest()
        )
    return path


def test_the_kernel_lives_under_naifs_own_name(tmp_path):
    assert local_path_for_leap_second_kernel(tmp_path) == tmp_path / "naif0012.tls"


def test_a_kernel_is_read_with_its_leap_seconds_and_input_record(tmp_path):
    kernel = read_leap_second_kernel_file(write_fake_kernel(tmp_path))
    assert kernel.tai_minus_utc_s == ((date(1972, 1, 1), 10), (date(1972, 7, 1), 11), (date(2017, 1, 1), 37))
    assert kernel.input_record.size_bytes == len(FAKE_KERNEL) and len(kernel.input_record.sha256) == 64


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("<html>404 Not Found</html>\n", "first line is not KPL/LSK"),
        ("KPL/LSK\nno table here\n", "no DELTET/DELTA_AT"),
    ],
    ids=["an HTML error page", "no table"],
)
def test_a_file_that_is_not_a_leap_second_kernel_raises(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        read_leap_second_kernel_file(write_fake_kernel(tmp_path, text))


def test_a_missing_kernel_without_download_says_how_to_get_it(tmp_path):
    with pytest.raises(FileNotFoundError, match="allow_download=True"):
        load_leap_second_kernel(tmp_path, allow_download=False)


def test_a_present_kernel_with_the_pinned_hash_loads_without_downloading(tmp_path, monkeypatch):
    write_fake_kernel(tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        spice_kernels, "download_leap_second_kernel", lambda directory: pytest.fail("downloaded")
    )
    assert load_leap_second_kernel(tmp_path, allow_download=True).tai_minus_utc_s[-1] == (
        date(2017, 1, 1),
        37,
    )


def test_a_kernel_with_a_different_hash_is_rejected(tmp_path):
    write_fake_kernel(tmp_path)  # the pinned hash is the real file's, not the fake's
    with pytest.raises(ValueError, match="not the expected naif0012.tls"):
        load_leap_second_kernel(tmp_path, allow_download=False)


def test_a_wrong_download_is_removed(tmp_path, monkeypatch):
    def fake_download(url, target):
        target.write_text("KPL/LSK\nsomething else\n", encoding="ascii")
        return target

    monkeypatch.setattr(spice_kernels, "download_file", fake_download)
    with pytest.raises(ValueError, match="removed"):
        load_leap_second_kernel(tmp_path, allow_download=True)
    assert not (tmp_path / LEAP_SECOND_KERNEL_NAME).exists()


@pytest.mark.network
def test_the_real_kernel_downloads_with_the_pinned_hash_and_28_leap_seconds(tmp_path):
    kernel = load_leap_second_kernel(tmp_path, allow_download=True)
    assert len(kernel.tai_minus_utc_s) == 28  # TAI − UTC from 10 s (1972) to 37 s (2017)
    assert kernel.tai_minus_utc_s[-1] == (date(2017, 1, 1), 37)
