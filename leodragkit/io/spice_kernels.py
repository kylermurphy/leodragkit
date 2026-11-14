"""NAIF SPICE kernels: the leap-second kernel ``naif0012.tls``, which time-scale conversions need (D-82).

Kept in the main config's ``spice_kernels`` data directory. The four functions follow the io template:
``local_path_for_leap_second_kernel``, ``download_leap_second_kernel``, ``read_leap_second_kernel_file``
and ``load_leap_second_kernel``.

**Freshness:** the file is treated as fixed once complete, and is never re-downloaded. NAIF publishes a
leap second as a *new* file with a new name (``naif0013.tls``), so taking one up is a deliberate change of
``LEAP_SECOND_KERNEL_NAME``, recorded as a decision. Its SHA-256 is pinned: a different or damaged file
is rejected, not used.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from leodragkit.io.http_download import download_file
from leodragkit.io.records import InputRecord, input_record_for

LEAP_SECOND_KERNEL_NAME = "naif0012.tls"
LEAP_SECOND_KERNEL_URL = f"https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/{LEAP_SECOND_KERNEL_NAME}"
# Of the file served at LEAP_SECOND_KERNEL_URL on 2026-11-02: 5257 bytes, last leap second 2017-01-01.
LEAP_SECOND_KERNEL_SHA256 = "678e32bdb5a744117a467cd9601cd6b373f0e9bc9bbde1371d5eee39600a039b"

# One entry of DELTET/DELTA_AT: TAI − UTC in seconds, and the UTC date it starts, as in "37, @2017-JAN-1".
_DELTA_AT_ENTRY = re.compile(r"(\d+)\s*,\s*@(\d{4})-([A-Z]{3})-(\d{1,2})")


@dataclass(frozen=True)
class LeapSecondKernel:
    """A checked leap-second kernel: where it is, what it says, and exactly which file it was."""

    path: Path
    tai_minus_utc_s: tuple[tuple[date, int], ...]  # (UTC date it starts, TAI − UTC in s), oldest first
    input_record: InputRecord


def local_path_for_leap_second_kernel(spice_kernel_directory: Path) -> Path:
    """Where the leap-second kernel lives: ``<spice_kernels>/naif0012.tls``, NAIF's own file name."""
    return Path(spice_kernel_directory) / LEAP_SECOND_KERNEL_NAME


def download_leap_second_kernel(spice_kernel_directory: Path) -> Path:
    """Download the leap-second kernel from NAIF into the directory, check its SHA-256, return its path.

    Raises
    ------
    ValueError
        If the downloaded file's SHA-256 is not ``LEAP_SECOND_KERNEL_SHA256``; the file is then removed.
    requests.RequestException, OSError
        From the download (``io/http_download.py``).
    """
    path = download_file(LEAP_SECOND_KERNEL_URL, local_path_for_leap_second_kernel(spice_kernel_directory))
    record = input_record_for(path)
    if record.sha256 != LEAP_SECOND_KERNEL_SHA256:
        path.unlink()
        raise ValueError(
            f"The file downloaded from {LEAP_SECOND_KERNEL_URL} is not the expected "
            f"{LEAP_SECOND_KERNEL_NAME} (SHA-256 {record.sha256}); it was removed. NAIF may have changed the "
            "file: check before using it."
        )
    return path


def read_leap_second_kernel_file(path: Path) -> LeapSecondKernel:
    """Read a NAIF leap-second kernel: check it is one, and list its leap seconds.

    Raises
    ------
    FileNotFoundError
        If there is no file.
    ValueError
        If the file is not a NAIF text leap-second kernel (its first line is not ``KPL/LSK``, as an HTML
        error page saved under the name would not be), or has no ``DELTET/DELTA_AT`` table.

    Example::

        kernel = read_leap_second_kernel_file(Path("D:/data/spice_kernels/naif0012.tls"))
        kernel.tai_minus_utc_s[-1]   # (datetime.date(2017, 1, 1), 37)
    """
    # 1. A NAIF leap-second kernel starts with the line KPL/LSK.
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"No leap-second kernel at {file_path}.")
    text = file_path.read_text(encoding="ascii", errors="replace")
    if text.split("\n", 1)[0].strip() != "KPL/LSK":
        raise ValueError(f"{file_path} is not a NAIF leap-second kernel: its first line is not KPL/LSK.")

    # 2. The DELTET/DELTA_AT table: from its assignment to the closing parenthesis.
    start = text.find("DELTET/DELTA_AT")
    end = text.find(")", start)
    if start < 0 or end < 0:
        raise ValueError(f"{file_path} has no DELTET/DELTA_AT table of leap seconds.")
    entries = [
        (datetime.strptime(f"{year}-{month}-{day}", "%Y-%b-%d").date(), int(seconds))
        for seconds, year, month, day in _DELTA_AT_ENTRY.findall(text[start:end])
    ]
    if not entries:
        raise ValueError(f"{file_path}: DELTET/DELTA_AT holds no leap seconds.")
    return LeapSecondKernel(
        path=file_path, tai_minus_utc_s=tuple(entries), input_record=input_record_for(file_path)
    )


def load_leap_second_kernel(spice_kernel_directory: Path, allow_download: bool) -> LeapSecondKernel:
    """The leap-second kernel from the data directory, downloaded first if missing and allowed.

    Raises
    ------
    FileNotFoundError
        If the file is missing and ``allow_download`` is false; the message says how to fix it.
    ValueError
        If the file is not the expected ``naif0012.tls`` (SHA-256), or not a leap-second kernel.

    Example::

        kernel = load_leap_second_kernel(main_config.data_directories.spice_kernels, allow_download=True)
    """
    # 1. The file, downloading it when missing and allowed.
    path = local_path_for_leap_second_kernel(spice_kernel_directory)
    if not path.is_file():
        if not allow_download:
            raise FileNotFoundError(
                f"The leap-second kernel {path} is missing. Call load_leap_second_kernel(..., "
                f"allow_download=True), or download {LEAP_SECOND_KERNEL_URL} into {path.parent}."
            )
        download_leap_second_kernel(spice_kernel_directory)

    # 2. Exactly the expected file, then read it.
    kernel = read_leap_second_kernel_file(path)
    if kernel.input_record.sha256 != LEAP_SECOND_KERNEL_SHA256:
        raise ValueError(
            f"{path} is not the expected {LEAP_SECOND_KERNEL_NAME} (SHA-256 {kernel.input_record.sha256}). "
            "Delete it and load again with allow_download=True."
        )
    return kernel
