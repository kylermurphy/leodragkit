"""The same instants on three time scales, UTC, GPS and SPICE ephemeris time (ET): ``Epochs``.

Spire's files are tagged in GPS time, the atmosphere model works in UTC, and SPICE (planetary ephemerides) in
ET. ``Epochs`` holds every instant on all three, so a number is never on an unknown scale (D-82). Build one
with ``epochs_from_utc``, ``epochs_from_gps`` or ``epochs_from_et``, giving the leap-second kernel from
``leodragkit.io.spice_kernels.load_leap_second_kernel``.

How the scales relate:

- **GPS = TAI − 19 s**, fixed since the GPS epoch (1980-01-06), so **GPS − UTC = (TAI − UTC) − 19 s**, which
  steps at each leap second (18 s since 2017-01-01). TAI − UTC comes from the kernel's table. Source: BIPM,
  "Relations of UTC and TAI with GPS time, GLONASS time, UTC(USNO)_GPS and UTC(SU)_GLONASS", BIPM Annual
  Report on Time Activities (https://www.bipm.org/documents/20126/59466374/23_utcgpsglo_TAR20.pdf, read
  2026-11-02): [TAI − GPS time] = 19 s + C0, with C0 tens of nanoseconds. ``Epochs.gps`` is the nominal
  scale, TAI − 19 s exactly; the nanosecond-level C0 of the broadcast GPS time is ignored.
- **ET** is SPICE's ephemeris time, TDB seconds past J2000. UTC ↔ ET goes through spiceypy (``str2et``,
  ``et2utc``), with the same kernel loaded into SPICE once.

UTC and GPS are held as ``datetime64[ns]`` calendar labels on their own scale; ET as float seconds (about
0.1 µs resolution today). A leap second itself (23:59:60 UTC) cannot be written as a ``datetime64``, so a GPS
or ET instant inside one raises rather than being shifted.

Read first: ``Epochs``, then ``epochs_from_gps`` and ``epochs_from_utc``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import spiceypy
from numpy.typing import ArrayLike

if TYPE_CHECKING:  # only for type hints: this module never imports io at run time
    from leodragkit.io.spice_kernels import LeapSecondKernel

# GPS time = TAI − 19 s, fixed (BIPM; see the module docstring).
TAI_MINUS_GPS_S = 19

_ONE_SECOND = np.timedelta64(1, "s")

# Kernels already given to SPICE, by resolved path: each is loaded once per session.
_loaded_kernel_paths: set[Path] = set()


@dataclass(frozen=True)
class Epochs:
    """N instants, each on three time scales. Build with ``epochs_from_utc``, ``_gps`` or ``_et``."""

    utc: np.ndarray  # (N,) datetime64[ns], UTC calendar
    gps: np.ndarray  # (N,) datetime64[ns], GPS calendar (no leap seconds)
    et_s: np.ndarray  # (N,) float64, SPICE ephemeris time: TDB seconds past J2000
    leap_second_kernel: str  # the kernel file used, for provenance

    def __post_init__(self) -> None:
        for name in ("utc", "gps"):
            values = getattr(self, name)
            if (
                not isinstance(values, np.ndarray)
                or values.dtype != np.dtype("datetime64[ns]")
                or values.ndim != 1
            ):
                raise ValueError(f"Epochs.{name} must be a one-dimensional datetime64[ns] array.")
        if not isinstance(self.et_s, np.ndarray) or self.et_s.dtype != np.float64 or self.et_s.ndim != 1:
            raise ValueError("Epochs.et_s must be a one-dimensional float64 array.")
        if not len(self.utc) == len(self.gps) == len(self.et_s):
            raise ValueError("Epochs.utc, gps and et_s must have the same length.")
        if np.any(np.isnat(self.utc)) or np.any(np.isnat(self.gps)) or not np.all(np.isfinite(self.et_s)):
            raise ValueError("Epochs must not contain NaT or non-finite values.")

    def __len__(self) -> int:
        return len(self.utc)


def epochs_from_utc(utc: ArrayLike, kernel: "LeapSecondKernel") -> Epochs:
    """``Epochs`` from UTC calendar times (``datetime64`` or ISO strings, without time zone).

    Raises
    ------
    ValueError
        If a time is before 1972-01-01 (the kernel's first leap-second entry), or not a valid time.

    Example::

        kernel = load_leap_second_kernel(main_config.data_directories.spice_kernels, allow_download=True)
        epochs = epochs_from_utc(["2023-10-31T13:57:18"], kernel)
        epochs.gps   # 2023-10-31T13:57:36: GPS is 18 s ahead of UTC since 2017
    """
    # 1. UTC as datetime64[ns], within the kernel's table.
    utc_ns = _as_datetime64_ns(utc, "utc")
    tai_minus_utc_s = _tai_minus_utc_at_utc(utc_ns, kernel)

    # 2. GPS = UTC + (TAI − UTC) − 19 s; ET from SPICE.
    gps = utc_ns + ((tai_minus_utc_s - TAI_MINUS_GPS_S) * _ONE_SECOND).astype("timedelta64[ns]")
    return Epochs(utc=utc_ns, gps=gps, et_s=_et_from_utc(utc_ns, kernel), leap_second_kernel=kernel.path.name)


def epochs_from_gps(gps: ArrayLike, kernel: "LeapSecondKernel") -> Epochs:
    """``Epochs`` from GPS calendar times, as Spire and SP3 files are tagged.

    Raises
    ------
    ValueError
        If a time falls inside a leap second (it would be 23:59:60 UTC, which ``datetime64`` cannot hold),
        or before 1972-01-01.

    Example::

        epochs = epochs_from_gps(["2023-10-31T13:57:36"], kernel)
        epochs.utc   # 2023-10-31T13:57:18
    """
    # 1. GPS as datetime64[ns]; where each leap second falls on the GPS scale.
    gps_ns = _as_datetime64_ns(gps, "gps")
    starts_utc, tai_minus_utc_s = _leap_table(kernel)
    # A new TAI − UTC value starts at UTC midnight: on the GPS scale, midnight + (TAI − UTC − 19) s.
    starts_gps = starts_utc + ((tai_minus_utc_s - TAI_MINUS_GPS_S) * _ONE_SECOND).astype("timedelta64[ns]")

    # 2. Which entry applies, and no instant inside a leap second (the GPS second just before a later entry).
    index = np.searchsorted(starts_gps, gps_ns, side="right") - 1
    if np.any(index < 0):
        raise ValueError(
            f"GPS time {gps_ns[np.argmax(index < 0)]} is before the leap-second table (1972-01-01)."
        )
    next_start = np.append(starts_gps[1:], np.datetime64("NaT", "ns"))[index]
    in_leap_second = ~np.isnat(next_start) & (gps_ns >= next_start - _ONE_SECOND)
    if np.any(in_leap_second):
        raise ValueError(
            f"GPS time {gps_ns[np.argmax(in_leap_second)]} falls inside a leap second (23:59:60 UTC), "
            "which a datetime64 UTC time cannot hold."
        )

    # 3. UTC = GPS − (TAI − UTC − 19 s); ET from SPICE.
    offset = ((tai_minus_utc_s[index] - TAI_MINUS_GPS_S) * _ONE_SECOND).astype("timedelta64[ns]")
    utc_ns = gps_ns - offset
    return Epochs(
        utc=utc_ns, gps=gps_ns, et_s=_et_from_utc(utc_ns, kernel), leap_second_kernel=kernel.path.name
    )


def epochs_from_et(et_s: ArrayLike, kernel: "LeapSecondKernel") -> Epochs:
    """``Epochs`` from SPICE ephemeris times (TDB seconds past J2000).

    Raises
    ------
    ValueError
        If a time falls inside a leap second, or before 1972-01-01.
    """
    # 1. ET → UTC strings through SPICE (nanosecond digits), then the GPS scale from UTC.
    et = np.asarray(et_s, dtype=float).ravel()
    if not np.all(np.isfinite(et)):
        raise ValueError("et_s must be finite.")
    _furnish(kernel)
    utc_strings = spiceypy.et2utc(et.tolist(), "ISOC", 9) if len(et) else []
    if isinstance(utc_strings, str):
        utc_strings = [utc_strings]
    leap = [text for text in utc_strings if ":60." in text]
    if leap:
        raise ValueError(f"ET falls inside a leap second ({leap[0]} UTC), which a datetime64 cannot hold.")
    epochs = epochs_from_utc(np.array(utc_strings, dtype="datetime64[ns]"), kernel)

    # 2. Keep the given ET exactly, not the round trip through a string.
    return Epochs(utc=epochs.utc, gps=epochs.gps, et_s=et, leap_second_kernel=epochs.leap_second_kernel)


def _et_from_utc(utc_ns: np.ndarray, kernel: "LeapSecondKernel") -> np.ndarray:
    """ET for UTC times, through SPICE's ``str2et`` on ISO strings (about 0.7 s per 86,400 times)."""
    _furnish(kernel)
    if len(utc_ns) == 0:
        return np.array([], dtype=float)
    return np.asarray(spiceypy.str2et(np.datetime_as_string(utc_ns, unit="ns").tolist()), dtype=float).ravel()


def _tai_minus_utc_at_utc(utc_ns: np.ndarray, kernel: "LeapSecondKernel") -> np.ndarray:
    """TAI − UTC in whole seconds at each UTC time, from the kernel's table."""
    starts_utc, tai_minus_utc_s = _leap_table(kernel)
    index = np.searchsorted(starts_utc, utc_ns, side="right") - 1
    if np.any(index < 0):
        raise ValueError(
            f"UTC time {utc_ns[np.argmax(index < 0)]} is before the leap-second table (1972-01-01)."
        )
    return tai_minus_utc_s[index]


def _leap_table(kernel: "LeapSecondKernel") -> tuple[np.ndarray, np.ndarray]:
    """The kernel's table as arrays: UTC start dates (datetime64[ns]) and TAI − UTC (int seconds)."""
    starts = np.array(
        [np.datetime64(start, "ns") for start, _ in kernel.tai_minus_utc_s], dtype="datetime64[ns]"
    )
    values = np.array([seconds for _, seconds in kernel.tai_minus_utc_s], dtype=np.int64)
    return starts, values


def _furnish(kernel: "LeapSecondKernel") -> None:
    """Give the kernel to SPICE once per session (SPICE keeps a global pool of loaded kernels)."""
    path = Path(kernel.path).resolve()
    if path not in _loaded_kernel_paths:
        spiceypy.furnsh(str(path))
        _loaded_kernel_paths.add(path)


def _as_datetime64_ns(values: ArrayLike, name: str) -> np.ndarray:
    """``values`` as a one-dimensional datetime64[ns] array; raise ValueError naming ``name``."""
    try:
        array = np.atleast_1d(np.asarray(values, dtype="datetime64[ns]")).ravel()
    except (ValueError, TypeError) as error:
        raise ValueError(f"{name} must be datetime64 values or ISO date-time strings: {error}") from None
    if np.any(np.isnat(array)):
        raise ValueError(f"{name} must not contain NaT.")
    return array
