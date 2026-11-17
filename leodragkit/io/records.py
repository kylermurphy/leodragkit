"""Records that ``io`` readers return: one dataclass per kind, whatever the file format (D-83).

- ``InputRecord``: which file was read, exactly (D-15).
- ``SatelliteStates``: positions and velocities over time (task I1; SP3 files first).
- ``AttitudeRecords``: quaternions over time exactly as a file writes them, with the file's conventions and a
  quality flag per epoch (task I2; Spire leoAtt files first). ``keep_observed`` keeps the observed epochs.
"""

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from leodragkit.io.repeated_warnings import warn_every_time
from leodragkit.time_scales import Epochs

# Frame labels a SatelliteStates may carry; defined in docs/plans/A4_attitude_and_flow_overview.md.
STATE_FRAMES = ("ITRF",)
ATTITUDE_FRAMES = ("ITRF", "orbit_level_spire")

# Quaternion conventions an AttitudeRecords must state (D-81): none has a default.
SCALAR_POSITIONS = ("first", "last")
QUATERNION_ALGEBRAS = ("hamilton", "jpl")
ROTATION_DIRECTIONS = ("body_to_reference", "reference_to_body")

# The meaning of a quality flag that keep_observed keeps; a reader maps its file's flags onto meanings.
OBSERVED = "observed"


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


class UnobservedAttitudeWarning(UserWarning):
    """``keep_observed`` left out attitude epochs that were not observed (repeated or default values).

    Shown every time. To make it an error: ``warnings.simplefilter("error", UnobservedAttitudeWarning)``.
    """


@dataclass(frozen=True)
class AttitudeRecords:
    """Attitude quaternions at N epochs, exactly as a file writes them, with the conventions to read them.

    ``io`` never interprets the quaternions: aero turns them into rotations from these conventions (A4a).
    Every epoch is kept with its quality flag, so the observed and the unobserved can both be saved;
    ``keep_observed`` gives the observed ones. Built by a reader; checked whenever created.

    Example::

        records = read_spire_attitude_file("spire_att_L1A_leoAtt_….log", kernel)
        observed = keep_observed(records)
    """

    epochs: Epochs  # the N instants, on UTC, GPS and SPICE ET
    quaternions: np.ndarray  # (N, 4) exactly as written, in the order scalar_position says
    scalar_position: str  # "first" or "last"
    algebra: str  # "hamilton" or "jpl"
    direction: str  # "body_to_reference" (u' = q u q* takes body vectors to the frame) or "reference_to_body"
    frame: str  # the reference frame, a label from ATTITUDE_FRAMES
    quality_flags: np.ndarray  # (N,) integers, as written
    flag_meanings: dict[
        int, str
    ]  # every flag the file's version defines, e.g. {0: "observed", 1: "repeated"}
    satellite_id: str  # e.g. "FM134"
    file_version: str  # e.g. "1.2", which set flag_meanings
    dropped_record_lines: tuple[
        int, ...
    ]  # line numbers of records the reader dropped (bad, unmatched, repeated)
    input_record: InputRecord  # the file read (D-15)

    def __post_init__(self) -> None:
        _check_attitude_records(self)

    def __len__(self) -> int:
        return len(self.epochs)


def keep_observed(records: AttitudeRecords) -> AttitudeRecords:
    """The epochs whose flag means "observed", as new ``AttitudeRecords``; ``records`` is left as it was.

    Warns
    -----
    UnobservedAttitudeWarning
        When any epoch is left out, with the counts by meaning (shown every time).

    Raises
    ------
    ValueError
        If no epoch was observed.

    Example::

        observed = keep_observed(records)   # e.g. 6284 of 7561 epochs; repeated 726 and default 551 left out
    """
    # 1. Which epochs were observed.
    observed_flags = [flag for flag, meaning in records.flag_meanings.items() if meaning == OBSERVED]
    keep = np.isin(records.quality_flags, observed_flags)
    if not np.any(keep):
        raise ValueError(f"{records.input_record.path.name}: no attitude epoch was observed.")

    # 2. Report what is left out, by meaning.
    if not np.all(keep):
        left_out = {
            records.flag_meanings[int(flag)]: int(count)
            for flag, count in zip(*np.unique(records.quality_flags[~keep], return_counts=True), strict=True)
        }
        counts = ", ".join(f"{meaning} {count}" for meaning, count in left_out.items())
        warn_every_time(
            f"{records.input_record.path.name}: kept {int(np.sum(keep))} observed attitude epochs of "
            f"{len(records)}; left out {counts}.",
            UnobservedAttitudeWarning,
            caller_depth=1,
        )

    # 3. The same records, at the observed epochs only.
    epochs = Epochs(
        utc=records.epochs.utc[keep],
        gps=records.epochs.gps[keep],
        et_s=records.epochs.et_s[keep],
        leap_second_kernel=records.epochs.leap_second_kernel,
    )
    return replace(
        records,
        epochs=epochs,
        quaternions=records.quaternions[keep],
        quality_flags=records.quality_flags[keep],
    )


def _check_attitude_records(records: AttitudeRecords) -> None:
    """Raise ValueError, naming the field, if an AttitudeRecords is inconsistent."""
    # 1. Epochs: at least one, strictly increasing.
    name = records.input_record.path.name if isinstance(records.input_record, InputRecord) else "?"
    count = len(records.epochs)
    if count == 0:
        raise ValueError(f"AttitudeRecords needs at least one epoch ({name}).")
    if np.any(np.diff(records.epochs.gps) <= np.timedelta64(0, "ns")):
        raise ValueError(f"AttitudeRecords epochs must be strictly increasing ({name}).")

    # 2. Quaternions (N, 4) and finite; flags (N,) integers, each one the version defines.
    quaternions = records.quaternions
    if not isinstance(quaternions, np.ndarray) or quaternions.shape != (count, 4):
        raise ValueError(
            f"AttitudeRecords.quaternions must have shape ({count}, 4), got {np.shape(quaternions)}."
        )
    if not np.all(np.isfinite(quaternions)):
        raise ValueError("AttitudeRecords.quaternions must be finite.")
    flags = records.quality_flags
    if (
        not isinstance(flags, np.ndarray)
        or flags.shape != (count,)
        or not np.issubdtype(flags.dtype, np.integer)
    ):
        raise ValueError(f"AttitudeRecords.quality_flags must be {count} integers.")
    if not records.flag_meanings or OBSERVED not in records.flag_meanings.values():
        raise ValueError(
            f"AttitudeRecords.flag_meanings must give at least one flag the meaning {OBSERVED!r}."
        )
    undefined = sorted(set(flags.tolist()) - set(records.flag_meanings))
    if undefined:
        raise ValueError(
            f"AttitudeRecords.quality_flags has flags {undefined} that flag_meanings does not define."
        )

    # 3. Conventions, frame and labels, from the fixed lists.
    for field, allowed in (
        ("scalar_position", SCALAR_POSITIONS),
        ("algebra", QUATERNION_ALGEBRAS),
        ("direction", ROTATION_DIRECTIONS),
        ("frame", ATTITUDE_FRAMES),
    ):
        if getattr(records, field) not in allowed:
            raise ValueError(
                f"AttitudeRecords.{field} must be one of {allowed}, got {getattr(records, field)!r}."
            )
    for field in ("satellite_id", "file_version"):
        if not isinstance(getattr(records, field), str) or not getattr(records, field):
            raise ValueError(f"AttitudeRecords.{field} must be a non-empty string.")
    if not all(isinstance(line, int) for line in records.dropped_record_lines):
        raise ValueError("AttitudeRecords.dropped_record_lines must be line numbers (integers).")
    if not isinstance(records.input_record, InputRecord):
        raise ValueError("AttitudeRecords.input_record must be an InputRecord.")
