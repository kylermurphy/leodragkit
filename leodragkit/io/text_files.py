"""Reading the lines of a text data file, plain or compressed (gzip, bzip2, xz), for every io reader.

The compression is recognised from the file's first bytes, not its name. Unix ``compress`` (.Z) and zip
archives are refused with a message saying to decompress them first. Lines come back without their line
endings, Windows ones included. Text is read as ASCII, as the data formats require; any other byte shows as
the Unicode replacement character, so a parser sees it and rejects the line rather than the file failing.
"""

import bz2
import gzip
import io
import lzma
from collections.abc import Iterator
from pathlib import Path

# The first bytes of each compressed format, and how to open it.
_COMPRESSED_OPENERS = {
    b"\x1f\x8b": gzip.open,
    b"BZh": bz2.open,
    b"\xfd7zXZ\x00": lzma.open,
}
_UNSUPPORTED_SIGNATURES = {b"\x1f\x9d": "Unix compress (.Z)", b"PK\x03\x04": "zip"}


def text_lines(path: str | Path, kind_of_file: str = "file") -> Iterator[str]:
    """The lines of a text file, without line endings, whether plain or compressed (gzip, bzip2, xz).

    ``kind_of_file`` names the file in the error for a missing one, e.g. "SP3 file".

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
        raise FileNotFoundError(f"No {kind_of_file} at {file_path}.")
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

    # 2. Text lines, as ASCII.
    raw = opener(file_path, "rb") if opener is not None else file_path.open("rb")
    with io.TextIOWrapper(raw, encoding="ascii", errors="replace") as text:
        for line in text:
            yield line.rstrip("\r\n")
