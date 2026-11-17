"""Reading Spire's Level 1A attitude files (``spire_att_L1A_leoAtt_*.log``) into ``AttitudeRecords``.

The files follow the CHAMP attitude format, with a quality flag added at the end of each time line (Spire
Global, *Attitude and Navigation Product Summary*, 2021, §2.1.2). Step plan:
``docs/plans/I2_spire_attitude.md``.

- **Header:** ``%spire version 1.2 …`` (the version decides what the flags mean), ``+satellite … FM134``,
  ``+data_____ sca``, ``+reference gps``, ``+first____``, ``+last_____`` and ``*comment:`` lines.
- **Records**, in pairs: ``tim yyyy mm dd hh mm ss.sssssss f`` (a GPS time, then the flag) and
  ``sca qx qy qz qw`` (scalar last; body vectors into the orbit level frame, u′ = q u q*; Hamilton, D-85).
- **End:** ``%eof``.

Read first: ``read_spire_attitude_header``.
"""

from dataclasses import dataclass

# What each flag means, by file version. Version 1.2's own header comments say: 0 valid observed data;
# 1 epoch missing, previous valid data used; 2 epoch missing, default quaternion used. Version 1.1 (the
# summary's example): 0 real, 1 default. An unknown version raises.
SPIRE_ATTITUDE_FLAG_MEANINGS = {
    "1.1": {0: "observed", 1: "default"},
    "1.2": {0: "observed", 1: "repeated", 2: "default"},
}

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
