"""Frames for the flow on a spacecraft: its attitude, its orbit states, and the rotations between frames.

aero works in **ITRF**, the Earth-fixed frame (D-79): the velocity relative to the co-rotating atmosphere is
the ITRF velocity itself (D-25). An ``Attitude`` holds ``body_from_reference``, the rotation that takes a
vector in its reference frame into body coordinates; ``OrbitStates`` holds positions and velocities. Both
carry their times on one named scale and a frame label, and aero checks that the two agree rather than
interpolating (D-80). aero never imports ``io`` or ``time_scales`` (D-04): the workflow builds these types
from ``io``'s records, giving times on one scale (for example ``epochs.gps`` and ``"GPS"``).

Read first: ``Attitude`` and ``attitude_from_quaternions``, then ``OrbitStates``, then the orbit frame
(``inertial_velocity_in_itrf``, ``itrf_from_orbit_level``), ``attitude_from_law``, and ``attitude_in_itrf``
with ``common_epochs``.
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

# The nominal mean angular velocity of the Earth, about the ITRF z axis: IERS Conventions (2003), IERS
# Technical Note 32 (McCarthy & Petit), Table 1.1, unchanged in the IAU 2009 system of astronomical constants.
# Nominal: it ignores day-length changes of a few parts in 1e8, micrometres per second in v + ω × r.
EARTH_ROTATION_RATE_RAD_PER_S = 7.292115e-5

# Body axes an attitude law may name: a sign and an axis.
BODY_AXES = {
    "+x": (1, 0, 0),
    "-x": (-1, 0, 0),
    "+y": (0, 1, 0),
    "-y": (0, -1, 0),
    "+z": (0, 0, 1),
    "-z": (0, 0, -1),
}


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


def inertial_velocity_in_itrf(positions_m: ArrayLike, velocities_m_per_s: ArrayLike) -> np.ndarray:
    """The inertial velocity, written in ITRF axes: v + ω_E × r, with ω_E along the ITRF z axis.

    An ITRF velocity is relative to the rotating Earth (and so to the co-rotating atmosphere, D-25); adding
    ω_E × r gives the velocity a non-rotating observer sees, still written in ITRF axes. Spire's orbit level
    frame is defined with it (D-85), so no inertial frame and no Earth-orientation data are needed (D-79).

    Parameters
    ----------
    positions_m, velocities_m_per_s
        (T, 3) in ITRF.

    Returns
    -------
    np.ndarray
        (T, 3) in m/s. At the equator, at 6.67e6 m, ω_E × r is about 486 m/s, eastward.

    Example::

        inertial_velocity_in_itrf([[6.67e6, 0, 0]], [[0, 0, 7.8e3]])   # [[0, 486.4, 7800]]
    """
    # 1. ω_E as a vector: (0, 0, EARTH_ROTATION_RATE_RAD_PER_S).
    w_E = np.array([0, 0, EARTH_ROTATION_RATE_RAD_PER_S])
    # 2. v + ω_E × r for every row (np.cross works row by row on (T, 3) arrays).
    return velocities_m_per_s + np.cross(w_E, positions_m)


def itrf_from_orbit_level(positions_m: ArrayLike, inertial_velocities_m_per_s: ArrayLike) -> Rotation:
    """The rotation from Spire's orbit level frame into ITRF, at each epoch.

    The orbit level frame (Spire's leoAtt header; D-85), built from the position r and the inertial velocity v
    (``inertial_velocity_in_itrf``):

        Z = −r / |r|                (nadir)
        Y = −(r × v) / |r × v|      (opposite the orbit's angular momentum)
        X = Y × Z                   (along the part of v perpendicular to r)

    X, Y and Z, written in ITRF, are the **columns** of the rotation matrix: ``rotation.apply([1, 0, 0])``
    is X in ITRF. Its inverse, ``rotation.inv()``, is orbit_from_ITRF.

    Raises
    ------
    ValueError
        If any r is zero, or any r × v is zero (v along r), where the frame is undefined; names the epoch.

    Example::

        rotation = itrf_from_orbit_level([[6.67e6, 0, 0]], [[0, 7.8e3, 0]])
        rotation.apply([1, 0, 0])   # [[0, 1, 0]]: X along the velocity
    """
    # 1. r and v as (T, 3) float arrays; r × v and the lengths |r| and |r × v|; raise for a zero one.
    r = np.atleast_2d(np.asarray(positions_m, dtype=float))
    v = np.atleast_2d(np.asarray(inertial_velocities_m_per_s, dtype=float))
    r_cross_v = np.cross(r, v)
    r_length = np.linalg.norm(r, axis=1)
    r_cross_v_length = np.linalg.norm(r_cross_v, axis=1)
    undefined = (r_length == 0) | (r_cross_v_length == 0)
    if np.any(undefined):
        epoch = int(np.flatnonzero(undefined)[0])
        raise ValueError(f"epoch {epoch}: r or r × v is 0, so the orbit frame is undefined there.")

    # 2. Z, Y and X as (T, 3) unit vectors, in that order.
    z_axis = -r / r_length[:, np.newaxis]  # nadir
    y_axis = -r_cross_v / r_cross_v_length[:, np.newaxis]  # opposite the orbit's angular momentum
    x_axis = np.cross(y_axis, z_axis)  # along the part of v perpendicular to r

    # 3. The matrices with X, Y, Z as columns, then the rotations.
    return Rotation.from_matrix(np.stack([x_axis, y_axis, z_axis], axis=-1))


def attitude_from_law(states: OrbitStates, *, along_velocity: str, towards_nadir: str) -> Attitude:
    """An ``Attitude`` in ITRF for a spacecraft held fixed in its orbit frame, when there is no attitude data.

    The body axis ``along_velocity`` points along the orbit frame's X (the flight direction), and the body
    axis ``towards_nadir`` along Z (nadir); the third body axis follows, so the axes stay right-handed.
    GRACE's leading satellite, for example, flies with body x against its velocity: ``along_velocity="-x"``.

    Parameters
    ----------
    states
        Positions and velocities in ITRF; the attitude has the same times and scale.
    along_velocity, towards_nadir
        Signed body axes from ``BODY_AXES`` (``"+x"``, ``"-z"``, …); they must be perpendicular.

    Raises
    ------
    ValueError
        If an axis is not in ``BODY_AXES``, or the two are not perpendicular (the same axis, or opposite).

    Example::

        attitude = attitude_from_law(states, along_velocity="+x", towards_nadir="+z")
        attitude.frame   # "ITRF"
    """
    # 1. The two body axes as unit vectors, and a check that they are perpendicular.
    along = _signed_axis(along_velocity)
    nadir = _signed_axis(towards_nadir)
    if abs(along @ nadir) > 0:
        raise ValueError(
            f"along_velocity {along_velocity!r} and towards_nadir {towards_nadir!r} must be perpendicular "
            "body axes."
        )

    # 2. body_from_orbit, the same at every epoch. Its columns say where orbit X, Y and Z point in the body:
    #    X → along, Z → nadir, and Y = Z × X → nadir × along (a rotation carries cross products with it).
    body_from_orbit = Rotation.from_matrix(np.column_stack([along, np.cross(nadir, along), nadir]))

    # 3. orbit_from_ITRF: the orbit frame built from r and the inertial velocity, then inverted.
    inertial = inertial_velocity_in_itrf(states.positions_m, states.velocities_m_per_s)
    orbit_from_itrf = itrf_from_orbit_level(states.positions_m, inertial).inv()

    # 4. Two hops, ITRF → orbit frame → body (scipy's a * b applies b first), on the states' times.
    return Attitude(
        times=states.times,
        time_scale=states.time_scale,
        body_from_reference=body_from_orbit * orbit_from_itrf,
        frame="ITRF",
        source=f"attitude law: {along_velocity} along velocity, {towards_nadir} towards nadir",
    )


def attitude_in_itrf(attitude: Attitude, states: OrbitStates) -> Attitude:
    """The attitude with ITRF as its reference frame, using the orbit states at the same epochs.

    An attitude already in ITRF is returned as it is. One in Spire's orbit level frame is turned into ITRF
    with the orbit frame built from the states (``itrf_from_orbit_level`` with the inertial velocity, D-85):

        body_from_ITRF = body_from_orbit · orbit_from_ITRF

    Raises
    ------
    ValueError
        If the attitude and the states do not share the same epochs on the same time scale
        (``check_same_epochs``; ``common_epochs`` keeps the shared ones).

    Example::

        attitude, states = common_epochs(spire_attitude, states)
        attitude_itrf = attitude_in_itrf(attitude, states)
    """
    # 1. The same instants, or nothing is combined (no interpolation, D-80).
    check_same_epochs(attitude, states)
    if attitude.frame == "ITRF":
        return attitude

    # 2. The orbit frame at each epoch, from r and the inertial velocity; then two hops, ITRF → orbit → body.
    inertial = inertial_velocity_in_itrf(states.positions_m, states.velocities_m_per_s)
    orbit_from_itrf = itrf_from_orbit_level(states.positions_m, inertial).inv()
    return Attitude(
        times=attitude.times,
        time_scale=attitude.time_scale,
        body_from_reference=attitude.body_from_reference * orbit_from_itrf,
        frame="ITRF",
        source=f"{attitude.source}, turned into ITRF with the orbit frame from {states.source}",
    )


def check_same_epochs(attitude: Attitude, states: OrbitStates) -> None:
    """Raise ValueError unless the attitude and the states have exactly the same times on the same scale.

    The message says how they differ and points to ``common_epochs``, which keeps the epochs both share.
    """
    if attitude.time_scale != states.time_scale:
        raise ValueError(
            f"The attitude's times are {attitude.time_scale} and the states' are {states.time_scale}: "
            "give both on one scale (from Epochs) before combining them."
        )
    if len(attitude) != len(states) or not np.array_equal(attitude.times, states.times):
        shared = len(np.intersect1d(attitude.times, states.times))
        raise ValueError(
            f"The attitude ({len(attitude)} epochs) and the states ({len(states)}) do not have the same "
            f"epochs; {shared} are shared. common_epochs(attitude, states) keeps those; nothing is "
            "interpolated."
        )


def common_epochs(attitude: Attitude, states: OrbitStates) -> tuple[Attitude, OrbitStates]:
    """The attitude and the states at the epochs both hold exactly: selection, not interpolation (D-80, D-86).

    Raises
    ------
    ValueError
        If the two are on different time scales, or share no epoch.

    Example::

        attitude, states = common_epochs(attitude, states)   # e.g. 666 shared seconds of 7561 and 3306
    """
    # 1. One scale, then the shared times and where they sit in each input.
    if attitude.time_scale != states.time_scale:
        raise ValueError(
            f"The attitude's times are {attitude.time_scale} and the states' are {states.time_scale}: "
            "give both on one scale before matching them."
        )
    shared, in_attitude, in_states = np.intersect1d(attitude.times, states.times, return_indices=True)
    if len(shared) == 0:
        raise ValueError(
            f"The attitude ({attitude.times[0]} to {attitude.times[-1]}) and the states "
            f"({states.times[0]} to {states.times[-1]}) share no epoch."
        )

    # 2. Both at those epochs; everything else is carried over unchanged.
    return (
        Attitude(
            times=shared,
            time_scale=attitude.time_scale,
            body_from_reference=attitude.body_from_reference[in_attitude],
            frame=attitude.frame,
            source=attitude.source,
        ),
        OrbitStates(
            times=shared,
            time_scale=states.time_scale,
            positions_m=states.positions_m[in_states],
            velocities_m_per_s=states.velocities_m_per_s[in_states],
            frame=states.frame,
            source=states.source,
        ),
    )


def _signed_axis(name: str) -> np.ndarray:
    """The unit vector for a signed body axis such as ``"+x"`` or ``"-z"``; raise ValueError otherwise."""
    if name not in BODY_AXES:
        raise ValueError(f"a body axis must be one of {sorted(BODY_AXES)}, got {name!r}.")
    return np.array(BODY_AXES[name], dtype=float)


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
