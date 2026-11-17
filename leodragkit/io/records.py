"""Records that ``io`` readers return: one dataclass per kind, whatever the file format (D-83).

- ``InputRecord``: which file was read, exactly (D-15).
- ``SatelliteStates``: positions and velocities over time (task I1; SP3 files first).
- ``AttitudeRecords`` joins this module in task I2.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from leodragkit.time_scales import Epochs

# Frame labels a SatelliteStates may carry; defined in docs/plans/A4_attitude_and_flow_overview.md.
STATE_FRAMES = ("ITRF",)


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


@dataclass(frozen=True)
class SatelliteStates:
    """A satellite's positions and velocities at N epochs, sorted by time, as every state reader returns.

    Velocities are required: a reader of a file without them raises, because deriving them would mean
    interpolating, which belongs to the workflow (D-80, D-83). Built by a reader; checked whenever created.

    Example::

        states = read_sp3_file("spire_nav_L1B_leoOrb_….sp3", kernel)
        states.epochs.utc[0], states.positions_m[0], states.frame   # …, [x, y, z] in metres, "ITRF"
    """

    epochs: Epochs  # the N instants, on UTC, GPS and SPICE ET
    positions_m: np.ndarray  # (N, 3) in the frame below
    velocities_m_per_s: np.ndarray  # (N, 3) in the frame below
    frame: str  # a label from STATE_FRAMES
    frame_as_written: str  # the file's own name for it, e.g. "IGS14", for provenance
    satellite_id: str  # the file's identifier, e.g. "L48"
    dropped_record_lines: tuple[
        int, ...
    ]  # line numbers of records the reader dropped (bad, unmatched, repeated)
    input_record: InputRecord  # the file read (D-15)

    def __post_init__(self) -> None:
        _check_satellite_states(self)

    def __len__(self) -> int:
        return len(self.epochs)


def _check_satellite_states(states: SatelliteStates) -> None:
    """Raise ValueError, naming the field, if a SatelliteStates is inconsistent."""
    # 1. Epochs: at least one, strictly increasing (so sorted, with no repeats).
    count = len(states.epochs)
    if count == 0:
        raise ValueError(f"SatelliteStates needs at least one epoch ({states.input_record.path.name}).")
    if np.any(np.diff(states.epochs.gps) <= np.timedelta64(0, "ns")):
        raise ValueError(
            f"SatelliteStates epochs must be strictly increasing ({states.input_record.path.name})."
        )

    # 2. Positions and velocities: (N, 3) and finite.
    for name in ("positions_m", "velocities_m_per_s"):
        values = getattr(states, name)
        if not isinstance(values, np.ndarray) or values.shape != (count, 3):
            raise ValueError(f"SatelliteStates.{name} must have shape ({count}, 3), got {np.shape(values)}.")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"SatelliteStates.{name} must be finite.")

    # 3. Labels and provenance.
    if states.frame not in STATE_FRAMES:
        raise ValueError(f"SatelliteStates.frame must be one of {STATE_FRAMES}, got {states.frame!r}.")
    for name in ("frame_as_written", "satellite_id"):
        if not isinstance(getattr(states, name), str) or not getattr(states, name):
            raise ValueError(f"SatelliteStates.{name} must be a non-empty string.")
    if not all(isinstance(line, int) for line in states.dropped_record_lines):
        raise ValueError("SatelliteStates.dropped_record_lines must be line numbers (integers).")
    if not isinstance(states.input_record, InputRecord):
        raise ValueError("SatelliteStates.input_record must be an InputRecord.")
