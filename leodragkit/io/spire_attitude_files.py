"""Reading Spire's Level 1A attitude files (``spire_att_L1A_leoAtt_*.log``) into ``AttitudeRecords``.

The files follow the CHAMP attitude format, with a quality flag added at the end of each time line (Spire
Global, *Attitude and Navigation Product Summary*, 2021, §2.1.2). Step plan:
``docs/plans/I2_spire_attitude.md``.

- **Header:** ``%spire version 1.2 …`` (the version decides what the flags mean), ``+satellite … FM134``,
  ``+data_____ sca``, ``+reference gps``, ``+first____``, ``+last_____`` and ``*comment:`` lines.
- **Records**, in pairs: ``tim yyyy mm dd hh mm ss.sssssss f`` (a GPS time, then the flag) and
  ``sca qx qy qz qw`` (scalar last; body vectors into the orbit level frame, u′ = q u q*; Hamilton, D-85).
- **End:** ``%eof``.

Read first: ``read_spire_attitude_file``, then ``read_spire_attitude_header``, ``_attitude_epoch`` and
``_attitude_quaternion``.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from leodragkit.io.records import AttitudeRecords, input_record_for
from leodragkit.io.repeated_warnings import warn_every_time
from leodragkit.io.text_files import text_lines
from leodragkit.time_scales import epochs_from_gps

# What each flag means, by file version. Version 1.2's own header comments say: 0 valid observed data;
# 1 epoch missing, previous valid data used; 2 epoch missing, default quaternion used. Version 1.1 (the
# summary's example): 0 real, 1 default. An unknown version raises.
SPIRE_ATTITUDE_FLAG_MEANINGS = {
    "1.1": {0: "observed", 1: "default"},
    "1.2": {0: "observed", 1: "repeated", 2: "default"},
}

# A quaternion whose length differs from 1 by more than this is a bad record (the user's file: within 6e-11).
QUATERNION_LENGTH_TOLERANCE = 1e-6

# The conventions every Spire leoAtt file uses (D-84, D-85), attached to the records it gives.
SPIRE_ATTITUDE_CONVENTIONS = {
    "scalar_position": "last",
    "algebra": "hamilton",
    "direction": "body_to_reference",
    "frame": "orbit_level_spire",
}


class AttitudeRecordsDroppedWarning(UserWarning):
    """A Spire attitude file had records that were dropped (bad, unmatched or repeated); the lines are kept.

    Shown every time. To make it an error: ``warnings.simplefilter("error", AttitudeRecordsDroppedWarning)``.
    """


@dataclass(frozen=True)
class SpireAttitudeHeader:
    """What a Spire leoAtt header says that leodragkit uses."""

    file_version: str  # e.g. "1.2"
    flag_meanings: dict[int, str]  # from SPIRE_ATTITUDE_FLAG_MEANINGS, by version
    satellite_id: str  # e.g. "FM134"
    first_record_line: int  # where the records start, counting from 1


def read_spire_attitude_file(path: str | Path, kernel) -> AttitudeRecords:
    """Read a Spire leoAtt file into ``AttitudeRecords``: every epoch, its quaternion as written, its flag.

    Each ``tim`` line is paired with the ``sca`` line after it. Dropped, with their line numbers kept in
    ``dropped_record_lines`` and counted in one ``AttitudeRecordsDroppedWarning``:

    - a pair whose ``sca`` is bad (``_attitude_quaternion`` gives None): both lines;
    - a ``tim`` with no ``sca`` before the next ``tim`` or the end;
    - an ``sca`` with no ``tim`` before it;
    - a later pair at an epoch already read: the first good one is kept.

    The records are sorted by time; every flag is kept (``keep_observed`` gives the observed epochs). The
    conventions every leoAtt file uses are attached (``SPIRE_ATTITUDE_CONVENTIONS``: scalar last, Hamilton,
    body to the orbit level frame; D-84, D-85).

    Parameters
    ----------
    path
        The leoAtt file: plain text, or gzip, bzip2 or xz compressed.
    kernel
        The leap-second kernel (``leodragkit.io.spice_kernels.load_leap_second_kernel``): the times are GPS,
        and ``Epochs`` needs it for UTC and SPICE ET.

    Raises
    ------
    ValueError
        For a header that cannot be used (``read_spire_attitude_header``), a malformed ``tim`` line, a flag
        the file's version does not define, or a line that is none of ``tim``, ``sca``, ``%eof`` or blank
        (each naming the line), or no good record at all.

    Example::

        kernel = load_leap_second_kernel(main_config.data_directories.spice_kernels, allow_download=True)
        records = read_spire_attitude_file("spire_att_L1A_leoAtt_v06_01_…_FM134.log", kernel)
        observed = keep_observed(records)
    """
    # 1. The lines and the header.
    file_path = Path(path).expanduser()
    lines = list(text_lines(file_path, "Spire attitude file"))
    header = read_spire_attitude_header(lines, file_path.name)

    # 2. Walk the records, pairing each tim with the sca after it (line numbers count from 1).
    epochs, quaternions, flags, dropped = [], [], [], []
    seen_epochs = set()
    pending = None  # (line number, epoch, flag) of a tim waiting for its sca
    for number, line in enumerate(lines[header.first_record_line - 1 :], start=header.first_record_line):
        if line.startswith("%eof"):
            break
        if not line.strip():
            continue
        if line.startswith("tim"):
            if pending is not None:
                dropped.append(pending[0])  # a tim left without its sca
            try:
                epoch, flag = _attitude_epoch(line)
            except ValueError as error:
                raise ValueError(f"{file_path.name}, line {number}: a malformed tim line: {error}") from None
            if flag not in header.flag_meanings:
                raise ValueError(
                    f"{file_path.name}, line {number}: flag {flag} is not one that version "
                    f"{header.file_version} defines ({header.flag_meanings})."
                )
            pending = (number, epoch, flag)
            continue
        if not line.startswith("sca"):
            raise ValueError(
                f"{file_path.name}, line {number}: expected a tim or sca line, got {line[:20]!r}."
            )

        # An sca line: it completes the pending tim, or stands alone.
        if pending is None:
            dropped.append(number)
            continue
        tim_number, epoch, flag = pending
        pending = None
        quaternion = _attitude_quaternion(line)
        if quaternion is None or epoch in seen_epochs:
            dropped.extend([tim_number, number])
            continue
        seen_epochs.add(epoch)
        epochs.append(epoch)
        quaternions.append(quaternion)
        flags.append(flag)
    if pending is not None:
        dropped.append(pending[0])

    # 3. At least one good record; sort by time.
    if not epochs:
        raise ValueError(f"{file_path.name}: no good tim and sca records.")
    times = np.array(epochs, dtype="datetime64[ns]")
    order = np.argsort(times, kind="stable")

    # 4. Report what was dropped, every time.
    dropped_lines = tuple(sorted(dropped))
    if dropped_lines:
        shown = ", ".join(str(line) for line in dropped_lines[:10])
        more = "" if len(dropped_lines) <= 10 else f" and {len(dropped_lines) - 10} more"
        warn_every_time(
            f"{file_path.name}: {len(dropped_lines)} attitude record lines were dropped (bad, unmatched or "
            f"repeated): lines {shown}{more}. Kept: {len(times)} epochs.",
            AttitudeRecordsDroppedWarning,
            caller_depth=1,
        )

    # 5. The records, on Epochs from GPS, with the conventions attached.
    return AttitudeRecords(
        epochs=epochs_from_gps(times[order], kernel),
        quaternions=np.array(quaternions)[order],
        quality_flags=np.array(flags, dtype=np.int64)[order],
        flag_meanings=header.flag_meanings,
        satellite_id=header.satellite_id,
        file_version=header.file_version,
        dropped_record_lines=dropped_lines,
        input_record=input_record_for(file_path),
        **SPIRE_ATTITUDE_CONVENTIONS,
    )


def read_spire_attitude_header(lines: list[str], file_name: str) -> SpireAttitudeHeader:
    """Read and check a Spire leoAtt header from the file's lines.

    The header is the opening lines starting ``%``, ``+`` or ``*``. Required: ``%spire version …`` with a
    known version, ``+satellite``, ``+data_____ sca`` and ``+reference gps``.

    Raises
    ------
    ValueError
        Naming the file: not a Spire attitude file, an unknown version, or a missing or unexpected
        satellite, data or reference line.

    Example::

        header = read_spire_attitude_header(list(text_lines(path)), path.name)
        header.file_version, header.satellite_id   # ("1.2", "FM134")
    """
    # 1. The header: its lines start '%', '+' or '*'; the first other line starts the records (so a stray
    #    record before the first tim is read, and dropped, rather than hidden in the header).
    header_prefixes = ("%", "+", "*")
    first_record = next(
        (n for n, line in enumerate(lines) if not line.startswith(header_prefixes)), len(lines)
    )
    header = lines[:first_record]
    if not header or not header[0].startswith("%spire"):
        raise ValueError(f"{file_name}: not a Spire attitude file (line 1 does not start with '%spire').")

    # 2. The version, the word after "version" on line 1, and what its flags mean.
    words = header[0].split()
    version = words[words.index("version") + 1] if "version" in words[:-1] else ""
    if version not in SPIRE_ATTITUDE_FLAG_MEANINGS:
        raise ValueError(
            f"{file_name}, line 1: Spire attitude version {version!r}; only "
            f"{sorted(SPIRE_ATTITUDE_FLAG_MEANINGS)} are read: the flags' meaning depends on the version."
        )

    # 3. The '+' lines: satellite (its last word), data type and time reference.
    fields = {
        line.split()[0]: line.split()[1:] for line in header if line.startswith("+") and line.split()[1:]
    }
    satellite = fields.get("+satellite", [])
    if not satellite:
        raise ValueError(f"{file_name}: no '+satellite' line, so no satellite.")
    if fields.get("+data_____") != ["sca"]:
        raise ValueError(
            f"{file_name}: '+data_____' must be 'sca' (quaternions), got {fields.get('+data_____')}."
        )
    if fields.get("+reference") != ["gps"]:
        raise ValueError(
            f"{file_name}: '+reference' must be 'gps' (GPS time), got {fields.get('+reference')}."
        )

    return SpireAttitudeHeader(
        file_version=version,
        flag_meanings=dict(SPIRE_ATTITUDE_FLAG_MEANINGS[version]),
        satellite_id=satellite[-1],
        first_record_line=first_record + 1,
    )


def _attitude_epoch(line: str) -> tuple[np.datetime64, int]:
    """The GPS time and the quality flag on a ``tim`` line.

    The line is eight fields separated by spaces (not fixed columns): ``tim``, year, month, day, hour,
    minute, seconds (with a fractional part), and the flag, e.g. ``tim 2023 12 18  7 57 18.0000000 2``.

    Raises
    ------
    ValueError
        If the line does not start with ``tim``, has not exactly eight fields, a field is not a number (the
        flag must be a whole number), the date or time does not exist, or the seconds are not from 0 to below
        60. The caller adds the file name and line number, and checks the flag against the file's version.

    Example::

        _attitude_epoch("tim 2023 12 18  7 57 18.0000000 2")   # (numpy.datetime64('2023-12-18T07:57:18…'), 2)
    """
    # 1. Split on spaces; check the first word and the number of fields.
    fields = line.split()
    if len(fields) != 8 or fields[0] != "tim":
        raise ValueError(f"a tim line has 8 fields starting 'tim', got {len(fields)} fields: {line!r}")

    # 2. Year, month, day, hour, minute and flag as whole numbers (int() rejects 2023.7 and 1.5, which a float
    #    first would quietly truncate); seconds as a float, from 0 to below 60.
    try:
        year, month, day, hour, minute, flag = (int(field) for field in (*fields[1:6], fields[7]))
        seconds = float(fields[6])
    except ValueError:
        raise ValueError(
            f"the date, time and flag must be numbers (the flag and date whole): {line!r}"
        ) from None
    if not 0 <= seconds < 60:  # 60 would be a leap second, which would otherwise roll into the next minute
        raise ValueError(f"seconds must be from 0 to below 60, got {seconds!r}")

    # 3. Whole minutes as a datetime64[ns], plus the seconds as integer nanoseconds (as in _sp3_epoch).
    epoch = np.datetime64(f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}", "ns")
    return epoch + np.timedelta64(round(seconds * 1e9), "ns"), flag


def _attitude_quaternion(line: str) -> np.ndarray | None:
    """The four numbers on an ``sca`` line, in the order written (qx, qy, qz, qw), or None for a bad record.

    The line is five fields separated by spaces: ``sca`` and the four components, e.g.
    ``sca -0.0083316449  0.0036622615  0.9929916885  0.1178332640``.

    Returns None, so the caller drops the record, when the line does not start with ``sca``, has not exactly
    five fields, a component is not a number or not finite, or the quaternion's length differs from 1 by more
    than ``QUATERNION_LENGTH_TOLERANCE``.

    Example::

        _attitude_quaternion("sca  0.0000000000  0.0000000000  0.0000000000  1.0000000000")
        # array([0., 0., 0., 1.])
    """
    # 1. Split on spaces; the number of fields first, so an empty line is simply bad.
    fields = line.split()
    if len(fields) != 5 or fields[0] != "sca":
        return None

    # 2. The four components as floats (a ValueError means a bad record: return None).
    try:
        quaternion = np.array([float(field) for field in fields[1:]])
    except ValueError:
        return None

    # 3. Finite, and of length 1 within the tolerance; otherwise None.
    if (
        not np.all(np.isfinite(quaternion))
        or abs(np.linalg.norm(quaternion) - 1.0) > QUATERNION_LENGTH_TOLERANCE
    ):
        return None
    return quaternion
