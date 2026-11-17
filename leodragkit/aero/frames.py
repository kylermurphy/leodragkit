"""Frames for the flow on a spacecraft: its attitude, its orbit states, and the rotations between frames.

aero works in **ITRF**, the Earth-fixed frame (D-79): the velocity relative to the co-rotating atmosphere is
the ITRF velocity itself (D-25). An ``Attitude`` holds ``body_from_reference``, the rotation that takes a
vector in its reference frame into body coordinates; ``OrbitStates`` holds positions and velocities. Both
carry their times on one named scale and a frame label, and aero checks that the two agree rather than
interpolating (D-80). aero never imports ``io`` or ``time_scales`` (D-04): the workflow builds these types
from ``io``'s records, giving times on one scale (for example ``epochs.gps`` and ``"GPS"``).

Read first: ``Attitude`` and ``attitude_from_quaternions``, then ``OrbitStates``.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy.spatial.transform import Rotation

# Frame labels (the documented list in docs/plans/A4_attitude_and_flow_overview.md, D-79).
ATTITUDE_FRAMES = ("ITRF", "orbit_level_spire")
STATE_FRAMES = ("ITRF",)

# Time-scale labels aero accepts: the times are compared, never converted, in aero.
TIME_SCALES = ("GPS", "UTC")

# Quaternion conventions (D-81), each a required argument with no default.
SCALAR_POSITIONS = ("first", "last")
QUATERNION_ALGEBRAS = ("hamilton", "jpl")
ROTATION_DIRECTIONS = ("body_to_reference", "reference_to_body")

# A quaternion whose length differs from 1 by more than this is rejected, not silently rescaled.
QUATERNION_LENGTH_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Attitude:
    """A spacecraft's orientation at T epochs: the rotation from a reference frame into the body frame.

    ``body_from_reference.apply(v)`` takes a vector ``v`` written in the reference frame and gives it in body
    coordinates. Build one with ``attitude_from_quaternions`` (attitude data) or the attitude law (A4a,
    component 2); checked whenever created.
    """

    times: np.ndarray  # (T,) datetime64[ns], strictly increasing
    time_scale: str  # the scale of ``times``, from TIME_SCALES
    body_from_reference: Rotation  # T rotations
    frame: str  # the reference frame, from ATTITUDE_FRAMES
    source: str  # where it came from, for provenance (e.g. a file name, or "attitude law: +x along velocity")

    def __post_init__(self) -> None:
        count = _check_times(self.times, self.time_scale, "Attitude")
        if not isinstance(self.body_from_reference, Rotation) or self.body_from_reference.single:
            raise ValueError(
                "Attitude.body_from_reference must be a scipy Rotation holding one rotation per epoch."
            )
        if len(self.body_from_reference) != count:
            raise ValueError(f"Attitude has {count} times but {len(self.body_from_reference)} rotations.")
        _check_label(self.frame, ATTITUDE_FRAMES, "Attitude.frame")
        _check_source(self.source, "Attitude")

    def __len__(self) -> int:
        return len(self.times)


@dataclass(frozen=True)
class OrbitStates:
    """A spacecraft's positions and velocities at T epochs, in the frame named (``"ITRF"``).

    aero's own copy of what ``io.records.SatelliteStates`` holds, so aero imports nothing from ``io`` (D-04);
    the workflow builds it, e.g. ``OrbitStates(states.epochs.gps, "GPS", states.positions_m,
    states.velocities_m_per_s, states.frame, states.input_record.path.name)``.
    """

    times: np.ndarray  # (T,) datetime64[ns], strictly increasing
    time_scale: str  # the scale of ``times``, from TIME_SCALES
    positions_m: np.ndarray  # (T, 3)
    velocities_m_per_s: np.ndarray  # (T, 3): in ITRF, the velocity relative to the co-rotating atmosphere
    frame: str  # from STATE_FRAMES
    source: str

    def __post_init__(self) -> None:
        count = _check_times(self.times, self.time_scale, "OrbitStates")
        for name in ("positions_m", "velocities_m_per_s"):
            values = getattr(self, name)
            if (
                not isinstance(values, np.ndarray)
                or values.shape != (count, 3)
                or not np.all(np.isfinite(values))
            ):
                raise ValueError(
                    f"OrbitStates.{name} must be finite with shape ({count}, 3), got {np.shape(values)}."
                )
        _check_label(self.frame, STATE_FRAMES, "OrbitStates.frame")
        _check_source(self.source, "OrbitStates")

    def __len__(self) -> int:
        return len(self.times)


def attitude_from_quaternions(
    times: ArrayLike,
    time_scale: str,
    quaternions: ArrayLike,
    *,
    scalar_position: str,
    algebra: str,
    direction: str,
    frame: str,
    source: str,
) -> Attitude:
    """An ``Attitude`` from quaternions written in a file's conventions, all three given explicitly (D-81).

    The quaternions are turned into ``body_from_reference`` in three steps:

    1. **Scalar position:** reordered to scalar last, as scipy expects.
    2. **Algebra:** read as Hamilton (i j = k). JPL multiplication (i j = −k) is Hamilton's in reverse order,
       so the rotation u′ = q u q* in JPL algebra is q* u q in Hamilton's: the inverse. A JPL quaternion is
       read as Hamilton and inverted.
    3. **Direction:** a quaternion taking body vectors into the reference frame (``"body_to_reference"``,
       as Spire's) is inverted; one taking reference vectors into the body frame is kept.

    Raises
    ------
    ValueError
        If a convention is not one of its listed values, the quaternions are not (T, 4) and finite, or one's
        length differs from 1 by more than ``QUATERNION_LENGTH_TOLERANCE`` (naming the first); scipy would
        otherwise rescale it silently into a plausible but wrong attitude.

    Example::

        attitude = attitude_from_quaternions(
            records.epochs.gps, "GPS", records.quaternions, scalar_position=records.scalar_position,
            algebra=records.algebra, direction=records.direction, frame=records.frame, source="FM134.log",
        )
    """
    # 1. The conventions, from their lists.
    _check_label(scalar_position, SCALAR_POSITIONS, "scalar_position")
    _check_label(algebra, QUATERNION_ALGEBRAS, "algebra")
    _check_label(direction, ROTATION_DIRECTIONS, "direction")

    # 2. The quaternions: (T, 4), finite, unit length.
    values = np.asarray(quaternions, dtype=float)
    if values.ndim != 2 or values.shape[1] != 4 or len(values) == 0:
        raise ValueError(f"quaternions must have shape (T, 4) with T ≥ 1, got {values.shape}.")
    if not np.all(np.isfinite(values)):
        raise ValueError("quaternions must be finite.")
    off_unit = np.abs(np.linalg.norm(values, axis=1) - 1.0) > QUATERNION_LENGTH_TOLERANCE
    if np.any(off_unit):
        index = int(np.flatnonzero(off_unit)[0])
        raise ValueError(
            f"quaternion {index} has length {np.linalg.norm(values[index]):.9g}; a rotation's must be 1 "
            "within "
            f"{QUATERNION_LENGTH_TOLERANCE}."
        )

    # 3. Scalar last, read as Hamilton; invert for JPL algebra and for a body-to-reference direction.
    scalar_last = values[:, [1, 2, 3, 0]] if scalar_position == "first" else values
    rotation = Rotation.from_quat(scalar_last)
    if algebra == "jpl":
        rotation = rotation.inv()
    if direction == "body_to_reference":
        rotation = rotation.inv()
    return Attitude(
        times=_as_times(times),
        time_scale=time_scale,
        body_from_reference=rotation,
        frame=frame,
        source=source,
    )


def _as_times(times: ArrayLike) -> np.ndarray:
    """``times`` as a one-dimensional datetime64[ns] array (checks follow in the type)."""
    return np.atleast_1d(np.asarray(times, dtype="datetime64[ns]")).ravel()


def _check_times(times, time_scale: str, owner: str) -> int:
    """Raise ValueError unless ``times`` is non-empty, increasing datetime64[ns], on a known scale."""
    if not isinstance(times, np.ndarray) or times.dtype != np.dtype("datetime64[ns]") or times.ndim != 1:
        raise ValueError(f"{owner}.times must be a one-dimensional datetime64[ns] array.")
    if len(times) == 0 or np.any(np.isnat(times)):
        raise ValueError(f"{owner}.times must hold at least one time, with no NaT.")
    if np.any(np.diff(times) <= np.timedelta64(0, "ns")):
        raise ValueError(f"{owner}.times must be strictly increasing.")
    _check_label(time_scale, TIME_SCALES, f"{owner}.time_scale")
    return len(times)


def _check_label(value, allowed: tuple[str, ...], name: str) -> None:
    """Raise ValueError naming ``name`` unless ``value`` is one of ``allowed``."""
    if value not in allowed:
        raise ValueError(f"{name} must be one of {allowed}, got {value!r}.")


def _check_source(source, owner: str) -> None:
    """Raise ValueError unless ``source`` is a non-empty string."""
    if not isinstance(source, str) or not source:
        raise ValueError(f"{owner}.source must be a non-empty string saying where the data came from.")
