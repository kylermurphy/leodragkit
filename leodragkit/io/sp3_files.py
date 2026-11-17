"""Reading SP3 orbit files (SP3-c and SP3-d) into ``SatelliteStates``: positions and velocities in metres.

SP3 is IGS's text format for satellite orbits; Spire delivers its precise orbits (leoOrb) and onboard
solutions (podObs) in it. Layout: Hilla, S., *The Extended Standard Product 3 Orbit Format (SP3-c)*, National
Geodetic Survey, NOAA, updated 17 August 2010, https://files.igs.org/pub/data/format/sp3c.txt. Step plan:
``docs/plans/I1_sp3_states.md``.

What is read, and checked (D-79, D-83, D-84):

- **Line 1:** the version (``#c`` or ``#d``), the velocity flag (``V``: velocities are required), and the
  coordinate system, mapped to a frame label (IGS08, IGb08, IGS14, IGb14, IGS20, ITR08, ITR14 and ITR20
  → ``"ITRF"``; the field is 5 columns wide, so ITRF2014 is written ITR14).
- **Line 3:** the number of satellites and their identifiers. Spire uses its 3-digit flight-module number
  (``134``) where IGS files use a letter and two digits (``G01``).
- **The first ``%c`` line:** the time system, ``GPS`` or ``UTC``.
- **Records:** ``*`` epochs, ``P`` positions in km, ``V`` velocities in dm/s, read by ``read_sp3_file`` into
  metres and metres per second. Bad records are dropped by the rules in ``read_sp3_file``, their line
  numbers kept, and one ``Sp3RecordsDroppedWarning`` summarises them.

Files may be plain text or compressed with gzip, bzip2 or xz, recognised from their first bytes
(``io/text_files.py``).

Read first: ``read_sp3_file``, then ``read_sp3_header``, ``_sp3_epoch`` and ``_sp3_vector``.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from leodragkit.io.records import SatelliteStates, input_record_for
from leodragkit.io.repeated_warnings import warn_every_time
from leodragkit.io.text_files import text_lines
from leodragkit.time_scales import epochs_from_gps, epochs_from_utc

# Coordinate-system names in SP3 headers (a 5-column field: ITRF2014 is written ITR14, as the specification's
# example ITR97) that are realisations of the ITRF, whose differences are millimetres. Any other name raises.
SP3_FRAME_NAMES = {
    name: "ITRF" for name in ("IGS08", "IGb08", "IGS14", "IGb14", "IGS20", "ITR08", "ITR14", "ITR20")
}
SP3_TIME_SYSTEMS = ("GPS", "UTC")
SP3_VERSIONS = ("c", "d")

# The specification's "bad or absent" clock value; treated as bad too if it appears in a position or velocity.
SP3_ABSENT_VALUE = 999999.999999


KILOMETRES_TO_METRES = 1000.0
DECIMETRES_PER_SECOND_TO_METRES_PER_SECOND = 0.1


class Sp3RecordsDroppedWarning(UserWarning):
    """An SP3 file had records that were dropped (bad, unmatched or repeated); the line numbers are kept.

    Shown every time, not only the first time from a given line. To make it an error:
    ``warnings.simplefilter("error", Sp3RecordsDroppedWarning)``.
    """


@dataclass(frozen=True)
class Sp3Header:
    """What an SP3 header says that leodragkit uses."""

    version: str  # "c" or "d"
    coordinate_system: str  # as written, e.g. "IGS08"
    frame: str  # the label it maps to, e.g. "ITRF"
    time_system: str  # "GPS" or "UTC"
    satellite_ids: tuple[str, ...]  # as written, e.g. ("134",) or ("G01", "G02", …)
    epoch_count: int  # as the header announces it (line 1); the records are counted separately


def read_sp3_file(path: str | Path, kernel, satellite_id: str | None = None) -> SatelliteStates:
    """Read one satellite's positions and velocities from an SP3 file, in metres, on ``Epochs``.

    Each ``P`` (position) record is paired with the ``V`` (velocity) record after it. Dropped, with their
    line numbers kept in ``dropped_record_lines`` and counted in one ``Sp3RecordsDroppedWarning``:

    - a pair whose ``P`` or ``V`` is bad (``_sp3_vector`` gives None): both lines;
    - a ``P`` with no ``V`` before the next record for the satellite, the next epoch or the end;
    - a ``V`` with no ``P`` before it;
    - a later pair at an epoch already read: the first good one is kept.

    The states are then sorted by time.

    Parameters
    ----------
    path
        The SP3 file: plain text, or gzip, bzip2 or xz compressed.
    kernel
        The leap-second kernel (``leodragkit.io.spice_kernels.load_leap_second_kernel``), for ``Epochs``.
    satellite_id
        Which satellite to read, as the file writes it (``"134"``, ``"G01"``). Required when the file
        holds more than one.

    Raises
    ------
    ValueError
        For a header that cannot be used (``read_sp3_header``), a missing or unknown ``satellite_id``, a
        malformed epoch line or a record before the first epoch (naming the line), or no good record at all.

    Example::

        kernel = load_leap_second_kernel(main_config.data_directories.spice_kernels, allow_download=True)
        states = read_sp3_file("spire_nav_L1B_leoOrb_v06_02_2023-12-18T09-51-49_FM134.sp3", kernel)
        states.frame_as_written, len(states)   # ("IGS08", 3306)
    """
    # 1. The lines, the header, and which satellite.
    file_path = Path(path).expanduser()
    lines = list(sp3_text_lines(file_path))
    header = read_sp3_header(lines, file_path.name)
    if satellite_id is None:
        if len(header.satellite_ids) != 1:
            raise ValueError(
                f"{file_path.name} holds {len(header.satellite_ids)} satellites; choose one with "
                "satellite_id "
                f"from {list(header.satellite_ids)}."
            )
        satellite_id = header.satellite_ids[0]
    elif satellite_id not in header.satellite_ids:
        raise ValueError(
            f"{file_path.name} has no satellite {satellite_id!r}; it has {list(header.satellite_ids)}."
        )

    # 2. Walk the records after the header, pairing P with the V after it (line numbers count from 1).
    epochs, positions, velocities, dropped = [], [], [], []
    seen_epochs = set()
    epoch = None
    pending = None  # (line number, the P values, or None if the P was bad)

    def drop_pending() -> None:
        nonlocal pending
        if pending is not None:
            dropped.append(pending[0])
            pending = None

    header_prefixes = ("#", "+", "%", "/*")  # header lines; the first other line starts the records
    first_record = next(
        (n for n, line in enumerate(lines) if not line.startswith(header_prefixes)), len(lines)
    )
    for number, line in enumerate(lines[first_record:], start=first_record + 1):
        if line.startswith("EOF"):
            break
        if line.startswith("*"):
            drop_pending()  # a P left without its V
            try:
                epoch = _sp3_epoch(line)
            except ValueError as error:
                raise ValueError(
                    f"{file_path.name}, line {number}: a malformed epoch line: {error}"
                ) from None
            continue
        if line[:1] not in ("P", "V") or line[1:4].strip() != satellite_id:
            continue  # another record type, or another satellite
        if epoch is None:
            raise ValueError(f"{file_path.name}, line {number}: a record before the first epoch line.")
        parsed = _sp3_vector(line)
        values = None if parsed is None else parsed[1]
        if line.startswith("P"):
            drop_pending()  # a second P before the V: the first had no V
            pending = (number, values)
            continue

        # A V line: it completes the pending P, or stands alone.
        if pending is None:
            dropped.append(number)
            continue
        p_number, p_values = pending
        pending = None
        if p_values is None or values is None or epoch in seen_epochs:
            dropped.extend([p_number, number])
            continue
        seen_epochs.add(epoch)
        epochs.append(epoch)
        positions.append(p_values * KILOMETRES_TO_METRES)
        velocities.append(values * DECIMETRES_PER_SECOND_TO_METRES_PER_SECOND)
    drop_pending()

    # 3. At least one good record; sort by time.
    if not epochs:
        raise ValueError(
            f"{file_path.name}: no good position and velocity records for satellite {satellite_id!r}."
        )
    order = np.argsort(np.array(epochs, dtype="datetime64[ns]"), kind="stable")
    times = np.array(epochs, dtype="datetime64[ns]")[order]

    # 4. Report what was dropped, every time.
    dropped_lines = tuple(sorted(dropped))
    if dropped_lines:
        shown = ", ".join(str(line) for line in dropped_lines[:10])
        more = "" if len(dropped_lines) <= 10 else f" and {len(dropped_lines) - 10} more"
        warn_every_time(
            f"{file_path.name}: {len(dropped_lines)} record lines for satellite {satellite_id!r} were "
            "dropped "
            f"(bad, unmatched or repeated): lines {shown}{more}. Kept: {len(times)} epochs.",
            Sp3RecordsDroppedWarning,
            caller_depth=1,
        )

    # 5. The states, on Epochs from the file's own time system.
    build_epochs = epochs_from_gps if header.time_system == "GPS" else epochs_from_utc
    return SatelliteStates(
        epochs=build_epochs(times, kernel),
        positions_m=np.array(positions)[order],
        velocities_m_per_s=np.array(velocities)[order],
        frame=header.frame,
        frame_as_written=header.coordinate_system,
        satellite_id=satellite_id,
        dropped_record_lines=dropped_lines,
        input_record=input_record_for(file_path),
    )


def read_sp3_header(lines: list[str], file_name: str) -> Sp3Header:
    """Read and check an SP3 file's header from its lines (the whole file, or at least its header).

    Raises
    ------
    ValueError
        Naming the file and the line: an unknown version, a file without velocities, a coordinate system
        that is not an ITRF realisation on the list, an unsupported time system, or a malformed header.

    Example::

        header = read_sp3_header(list(sp3_text_lines(path)), path.name)
        header.coordinate_system, header.frame, header.time_system   # ("IGS08", "ITRF", "GPS")
    """
    # 1. The header runs to the first epoch line ('*'); line 1: version, velocity flag, epochs, coordinates.
    header_end = next((number for number, line in enumerate(lines) if line.startswith("*")), len(lines))
    lines = lines[:header_end]
    if not lines or not lines[0].startswith("#"):
        raise ValueError(f"{file_name}: not an SP3 file (line 1 does not start with '#').")
    first = lines[0]
    version = first[1:2]
    if version not in SP3_VERSIONS:
        raise ValueError(f"{file_name}, line 1: SP3 version {version!r}; only {list(SP3_VERSIONS)} are read.")
    if first[2:3] != "V":
        raise ValueError(
            f"{file_name}, line 1: the file has no velocities (flag {first[2:3]!r}, not 'V'). "
            "Velocities are required; deriving them would mean interpolating, which is the workflow's job."
        )
    try:
        epoch_count = int(first[32:39])
    except ValueError:
        raise ValueError(f"{file_name}, line 1: columns 33–39 should hold the number of epochs.") from None
    coordinate_system = first[46:51].strip()
    if coordinate_system not in SP3_FRAME_NAMES:
        raise ValueError(
            f"{file_name}, line 1: coordinate system {coordinate_system!r} is not on the list of ITRF "
            f"realisations {sorted(SP3_FRAME_NAMES)}."
        )

    # 2. Line 3 onwards ('+ ' lines): the number of satellites and their identifiers, 3 characters each from
    #    column 10. Columns 4–6 hold the count (SP3-c uses 5–6, which the same slice reads).
    plus_lines = [line for line in lines[2:] if line.startswith("+ ")]
    try:
        satellite_count = int(lines[2][3:6]) if lines[2:3] and lines[2].startswith("+ ") else -1
        if satellite_count < 1:
            raise ValueError
    except ValueError:
        raise ValueError(f"{file_name}, line 3: columns 4–6 should hold the number of satellites.") from None
    identifiers = [line[9 + 3 * k : 12 + 3 * k].strip() for line in plus_lines for k in range(17)]
    satellite_ids = tuple(identifier for identifier in identifiers if identifier and identifier != "0")
    if len(satellite_ids) < satellite_count:
        raise ValueError(
            f"{file_name}: the header announces {satellite_count} satellites but lists {len(satellite_ids)}."
        )

    # 3. The first %c line: the time system, columns 10–12.
    time_lines = [line for line in lines if line.startswith("%c")]
    if not time_lines:
        raise ValueError(f"{file_name}: no '%c' line, so no time system.")
    time_system = time_lines[0][9:12].strip()
    if time_system not in SP3_TIME_SYSTEMS:
        raise ValueError(
            f"{file_name}: time system {time_system!r}; only {list(SP3_TIME_SYSTEMS)} are read for now."
        )

    return Sp3Header(
        version=version,
        coordinate_system=coordinate_system,
        frame=SP3_FRAME_NAMES[coordinate_system],
        time_system=time_system,
        satellite_ids=satellite_ids[:satellite_count],
        epoch_count=epoch_count,
    )


def sp3_text_lines(path: str | Path) -> Iterator[str]:
    """The lines of an SP3 file, without line endings, whether plain or compressed (``io/text_files.py``)."""
    return text_lines(path, "SP3 file")


def _sp3_epoch(line: str) -> np.datetime64:
    """The time on an epoch line (``*``), as a ``datetime64[ns]`` on the file's own time scale.

    Columns (SP3-c specification, "Line Twenty three"): 4–7 year, 9–10 month, 12–13 day, 15–16 hour,
    18–19 minute, 21–31 seconds (with a fractional part, e.g. ``13.00000000``).

    Raises
    ------
    ValueError
        If a field is missing or is not a number, the date or time does not exist, or the seconds are not
        from 0 to below 60 (a leap second, 60, cannot be held as a datetime64). The caller adds the file
        name and line number.

    Example::

        _sp3_epoch("*  2023 12 18  9 52 13.00000000")   # numpy.datetime64('2023-12-18T09:52:13.000000000')
    """
    # 1. The six fields, by column (Python slices count from 0: columns 4–7 are line[3:7]).
    year = int(line[3:7])
    month = int(line[8:10])
    day = int(line[11:13])
    hour = int(line[14:16])
    minute = int(line[17:19])
    seconds = float(line[20:31])
    if not 0 <= seconds < 60:  # 60 would be a leap second, which would otherwise roll into the next minute
        raise ValueError(f"seconds must be from 0 to below 60, got {seconds!r}")

    # 2. Whole minutes as a datetime64, np.datetime64(f"{year:04d}-{month:02d}-…", "ns"); a bad date raises.
    epoch = np.datetime64(f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}", "ns")

    # 3. Add the seconds as integer nanoseconds: round(seconds * 1e9), so 13.00000000 is exactly 13 s.
    return epoch + np.timedelta64(round(seconds * 1e9), "ns")


def _sp3_vector(line: str) -> tuple[str, np.ndarray] | None:
    """The satellite id and the three values on a ``P`` or ``V`` line, in the file's units, or None if bad.

    Columns (SP3-c specification, "Line Twenty four" and "Line Twenty six"): 2–4 the satellite id (``134``,
    ``G01``), 5–18 x, 19–32 y, 33–46 z: km for ``P``, dm/s for ``V``. The clock in 47–60 is not read.

    Returns None, so the caller drops the record, when any of x, y and z is blank, not a number or not finite,
    when all three are 0.000000 (the specification's "bad or absent"), or when one is ``SP3_ABSENT_VALUE``.

    Example::

        _sp3_vector("P134   6631.941824    281.807651   -657.598319  -4211.294181")
        # ("134", array([6631.941824, 281.807651, -657.598319]))
    """
    # 1. The id from columns 2–4, without spaces.
    satellite_id = line[1:4].strip()

    # 2. x, y and z from their 14-column fields; a blank, short or unparsable field means a bad record
    #    (a short line gives an empty slice, which float() rejects too).
    try:
        values = np.array([float(line[4:18]), float(line[18:32]), float(line[32:46])])
    except ValueError:
        return None

    # 3. Bad or absent: not finite, all three exactly 0, or the absent value anywhere (compared as a number,
    #    so every way of writing it is caught).
    if not np.all(np.isfinite(values)) or np.all(values == 0) or np.any(values == SP3_ABSENT_VALUE):
        return None
    return satellite_id, values
