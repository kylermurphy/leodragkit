"""Records that ``io`` readers return. For now: the input record of a file read (D-15).

``SatelliteStates`` and ``AttitudeRecords`` join this module in tasks I1 and I2 (D-83).
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class InputRecord:
    """Which file was read, exactly: enough to tell later whether it has changed (D-15)."""

    path: Path  # absolute
    size_bytes: int
    modified_utc: datetime  # the file's modification time
    sha256: str  # hex digest of the file's bytes


def input_record_for(path: Path) -> InputRecord:
    """The input record of an existing file: its absolute path, size, modification time and SHA-256."""
    file_path = Path(path).expanduser().resolve()
    status = file_path.stat()
    return InputRecord(
        path=file_path,
        size_bytes=status.st_size,
        modified_utc=datetime.fromtimestamp(status.st_mtime, tz=UTC),
        sha256=hashlib.sha256(file_path.read_bytes()).hexdigest(),
    )
