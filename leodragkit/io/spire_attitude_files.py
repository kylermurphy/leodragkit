"""Reading Spire's Level 1A attitude files (``spire_att_L1A_leoAtt_*.log``) into ``AttitudeRecords``.

The files follow the CHAMP attitude format, with a quality flag added at the end of each time line (Spire
Global, *Attitude and Navigation Product Summary*, 2021, §2.1.2). Step plan:
``docs/plans/I2_spire_attitude.md``.

- **Header:** ``%spire version 1.2 …`` (the version decides what the flags mean), ``+satellite … FM134``,
  ``+data_____ sca``, ``+reference gps``, ``+first____``, ``+last_____`` and ``*comment:`` lines.
- **Records**, in pairs: ``tim yyyy mm dd hh mm ss.sssssss f`` (a GPS time, then the flag) and
  ``sca qx qy qz qw`` (scalar last; body vectors into the orbit level frame, u′ = q u q*; Hamilton, D-85).
- **End:** ``%eof``.

Read first: ``read_spire_attitude_header``, then ``_attitude_epoch`` and ``_attitude_quaternion``.
"""

from dataclasses import dataclass

import numpy as np

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


@dataclass(frozen=True)
class SpireAttitudeHeader:
    """What a Spire leoAtt header says that leodragkit uses."""

    file_version: str  # e.g. "1.2"
    flag_meanings: dict[int, str]  # from SPIRE_ATTITUDE_FLAG_MEANINGS, by version
    satellite_id: str  # e.g. "FM134"
    first_record_line: int  # where the records start, counting from 1


def read_spire_attitude_header(lines: list[str], file_name: str) -> SpireAttitudeHeader:
    """Read and check a Spire leoAtt header from the file's lines.

    The header runs to the first ``tim`` line. Required: ``%spire version …`` with a known version,
    ``+satellite``, ``+data_____ sca`` and ``+reference gps``.

    Raises
    ------
    ValueError
        Naming the file: not a Spire attitude file, an unknown version, or a missing or unexpected
        satellite, data or reference line.

    Example::

        header = read_spire_attitude_header(list(text_lines(path)), path.name)
        header.file_version, header.satellite_id   # ("1.2", "FM134")
    """
    # 1. The header: everything before the first record.
    first_record = next((number for number, line in enumerate(lines) if line.startswith("tim")), len(lines))
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
    vals = line.split()
    if len(vals) != 8:
        raise(ValueError("Line should have 8 fields"))
    elif vals[0] != 'tim':
        raise(ValueError("Line should start with 'tim'"))

    # 2. Year, month, day, hour and minute as int; seconds as float, from 0 to below 60; the flag as int.
    try:
        n_values = [float(x) for x in vals[1:]]
    except ValueError:
        raise(ValueError("Times must be a number"))

    year = int(n_values[0])
    month = int(n_values[1])
    day = int(n_values[2])
    hour = int(n_values[3])
    minute = int(n_values[4])
    seconds = n_values[5]
    if not n_values[6].is_integer():
        raise(ValueError("Flag must be an integer"))
    flag = int(n_values[6])
    if not 0 <= seconds < 60:  # 60 would be a leap second, which would otherwise roll into the next minute
        raise ValueError(f"seconds must be from 0 to below 60, got {seconds!r}")


    # 3. Whole minutes as a datetime64[ns], plus the seconds as integer nanoseconds (as in _sp3_epoch).
    epoch = np.datetime64(f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}", "ns")
    epoch = epoch + np.timedelta64(round(seconds * 1e9), "ns")
    return epoch, flag


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
    # 1. Split on spaces; the first word and the number of fields.
    vals = line.split()
    if vals[0] != 'sca':
        return None
    elif len(vals) != 5:
        return None

    # 2. The four components as floats (a ValueError means a bad record: return None).
    try:
        quaternion = np.array([float(x) for x in vals[1:]])
    except ValueError:
        return None

    # 3. Finite, and of length 1 within the tolerance; otherwise None.
    if not np.all(np.isfinite(quaternion)):
        return None
    if not np.allclose(np.linalg.norm(quaternion),1,rtol=QUATERNION_LENGTH_TOLERANCE):
        return None
    return quaternion
