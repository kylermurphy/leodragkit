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
- **Records** (``*`` epochs, ``P`` positions in km, ``V`` velocities in dm/s) follow in later components.

Files may be plain text or compressed with gzip, bzip2 or xz, recognised from their first bytes.

Read first: ``read_sp3_header``.
"""

import bz2
import gzip
import io
import lzma
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Coordinate-system names in SP3 headers (a 5-column field: ITRF2014 is written ITR14, as the specification's
# example ITR97) that are realisations of the ITRF, whose differences are millimetres. Any other name raises.
SP3_FRAME_NAMES = {
    name: "ITRF" for name in ("IGS08", "IGb08", "IGS14", "IGb14", "IGS20", "ITR08", "ITR14", "ITR20")
}
SP3_TIME_SYSTEMS = ("GPS", "UTC")
SP3_VERSIONS = ("c", "d")

# The first bytes of each compressed format, and how to open it as text.
_COMPRESSED_OPENERS = {
    b"\x1f\x8b": gzip.open,
    b"BZh": bz2.open,
    b"\xfd7zXZ\x00": lzma.open,
}
_UNSUPPORTED_SIGNATURES = {b"\x1f\x9d": "Unix compress (.Z)", b"PK\x03\x04": "zip"}


@dataclass(frozen=True)
class Sp3Header:
    """What an SP3 header says that leodragkit uses."""

    version: str  # "c" or "d"
    coordinate_system: str  # as written, e.g. "IGS08"
    frame: str  # the label it maps to, e.g. "ITRF"
    time_system: str  # "GPS" or "UTC"
    satellite_ids: tuple[str, ...]  # as written, e.g. ("134",) or ("G01", "G02", …)
    epoch_count: int  # as the header announces it (line 1); the records are counted separately


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
    """The lines of an SP3 file, without line endings, whether plain or compressed (gzip, bzip2, xz).

    Raises
    ------
    FileNotFoundError
        If there is no file.
    ValueError
        If the file is Unix-compressed (.Z) or a zip archive, which are not read.
    """
    # 1. The format, from the first bytes.
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"No SP3 file at {file_path}.")
    with file_path.open("rb") as file:
        start = file.read(8)
    for signature, kind in _UNSUPPORTED_SIGNATURES.items():
        if start.startswith(signature):
            raise ValueError(
                f"{file_path.name} is {kind}-compressed, which is not read; decompress it first."
            )
    opener = next(
        (open_ for signature, open_ in _COMPRESSED_OPENERS.items() if start.startswith(signature)), None
    )

    # 2. Text lines, ASCII as the format requires (anything else shows as a replacement character).
    raw = opener(file_path, "rb") if opener is not None else file_path.open("rb")
    with io.TextIOWrapper(raw, encoding="ascii", errors="replace") as text:
        for line in text:
            yield line.rstrip("\r\n")
