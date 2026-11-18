"""Frames for the flow on a spacecraft: its attitude, its orbit states, and the rotations between frames.

aero works in **ITRF**, the Earth-fixed frame (D-79): the velocity relative to the co-rotating atmosphere is
the ITRF velocity itself (D-25). An ``Attitude`` holds ``body_from_reference``, the rotation that takes a
vector in its reference frame into body coordinates; ``OrbitStates`` holds positions and velocities. Both
carry their times on one named scale and a frame label, and aero checks that the two agree rather than
interpolating (D-80). aero never imports ``io`` or ``time_scales`` (D-04): the workflow builds these types
from ``io``'s records, giving times on one scale (for example ``epochs.gps`` and ``"GPS"``).

Read first: ``Attitude`` and ``attitude_from_quaternions``, then ``OrbitStates``, then the orbit frame
(``inertial_velocity_in_itrf``, ``itrf_from_orbit_level``), ``attitude_from_law``, and ``attitude_in_itrf``
with ``common_epochs``. Last, the flow on each panel (A4b): ``PanelFlowGeometry``, ``panel_flow_geometry``
and ``incidence_and_shear``.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy.spatial.transform import Rotation

from leodragkit.aero.geometry import PanelSet

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

# How far from 1 (or 0) a unit (or zero) vector's length may be, after floating-point arithmetic.
UNIT_LENGTH_TOLERANCE = 1e-9

# A projected flow shorter than this has no direction on the panel: the flow is along the normal (sin δ ≈ 0),
# and the shear direction is set to zero (the shear coefficient is zero there anyway).
SHEAR_PROJECTION_TOLERANCE = 1e-12

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
    states.velocities_m_per_s, states.frame, source_names(states))``, with ``source_names`` from
    ``leodragkit.io.records``.
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


@dataclass(frozen=True)
class PanelFlowGeometry:
    """How the flow meets each of N panels at each of T epochs, in the body frame: the gas-surface input.

    With v_rel the velocity relative to the air in the body frame (D-50, D-79):

    - ``speed_m_per_s`` is V = |v_rel|, and ``flow_direction`` is û = −v_rel / V, the way the air moves past;
    - ``cos_incidence`` is cos δ = n̂ · v_rel / V = −n̂ · û: +1 facing the flow squarely (ram), 0 edge-on
      (the flow skims along the panel), negative facing away (wake);
    - ``shear_directions`` is t̂, û projected onto the panel and made unit length, or zero where the flow is
      along the normal (sin δ = 0). So û · t̂ = sin δ = √(1 − cos²δ), which the checks confirm.

    Built by ``panel_flow_geometry`` for whatever epochs it is given; ``drag_area`` (A5) feeds it chunks
    (D-54, D-88). Per-epoch centroids are not held: nothing here needs them (D-88).
    """

    times: np.ndarray  # (T,) datetime64[ns], strictly increasing
    time_scale: str  # from TIME_SCALES
    speed_m_per_s: np.ndarray  # (T,), positive
    flow_direction: np.ndarray  # (T, 3), unit vectors
    cos_incidence: np.ndarray  # (T, N), in [−1, 1]
    shear_directions: np.ndarray  # (T, N, 3), unit vectors or zero
    source: str  # the attitude and orbit it came from

    def __post_init__(self) -> None:
        _check_panel_flow_geometry(self)

    def __len__(self) -> int:
        return len(self.times)

    @property
    def panel_count(self) -> int:
        return self.cos_incidence.shape[1]


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


def panel_flow_geometry(panel_set: PanelSet, attitude: Attitude, states: OrbitStates) -> PanelFlowGeometry:
    """How the flow meets each panel at each epoch: speed, flow direction, cos δ and shear direction (D-88).

    The velocity relative to the air is the ITRF velocity (the atmosphere co-rotates, D-25, D-79); the
    attitude turns it into the body frame, where the panels' normals are.

    Parameters
    ----------
    panel_set
        The spacecraft's N panels in its body frame.
    attitude
        ``body_from_reference`` with reference ``"ITRF"`` (a Spire attitude goes through ``attitude_in_itrf``
        first), at exactly the states' epochs.
    states
        Positions and velocities in ITRF.

    Raises
    ------
    ValueError
        If the attitude is not in ITRF, the epochs or time scales differ (``check_same_epochs``), or a speed
        is zero, naming the first such epoch.

    Memory: the shear directions are (T, N, 3) floats, about 20 GB for a day at 1 Hz with 10,000 panels.
    Give it chunks of epochs (``drag_area``, A5, does): the result for a slice of epochs equals the same rows
    of the full result.

    Example::

        geometry = panel_flow_geometry(spacecraft.panel_set, attitude_in_itrf(attitude, states), states)
        geometry.cos_incidence[0]   # cos δ of every panel at the first epoch
    """
    # 1. The attitude in ITRF, on exactly the states' epochs.
    if attitude.frame != "ITRF":
        raise ValueError(
            f"The attitude's reference frame is {attitude.frame!r}; turn it into ITRF first (attitude_in_itrf)."
        )
    check_same_epochs(attitude, states)
    att_com, states_com = common_epochs(attitude,states)

    # 2. The relative velocity in the body frame:
    #    attitude.body_from_reference.apply(states.velocities_m_per_s).
    v_rel = att_com.body_from_reference.apply(states_com.velocities_m_per_s)
    # 3. The speed V = |v| for each epoch; raise ValueError naming the first epoch where it is 0.
    speed = np.linalg.norm(v_rel, axis=1)
    if np.any(speed == 0):
        raise ValueError(f"epoch {int(np.flatnonzero(speed == 0)[0])}: zero speed, so no flow direction.")
    # 4. The flow direction û = −v / V.
    flow = -v_rel / speed[:, np.newaxis]

    # 5. cos δ and t̂ from incidence_and_shear, with the panel set's (N, 3) normals.
    cos_incidence, shear_directions = incidence_and_shear(panel_set.outward_normals, flow)
    # 6. A PanelFlowGeometry with the attitude's times and scale, and a source naming the attitude and states.
    return PanelFlowGeometry(
        times=attitude.times,
        time_scale=attitude.time_scale,
        speed_m_per_s=speed,
        flow_direction=flow,
        cos_incidence=cos_incidence,
        shear_directions=shear_directions,
        source=f"attitude: {attitude.source}; orbit: {states.source}",
    )


def incidence_and_shear(
    outward_normals: ArrayLike, flow_direction: ArrayLike
) -> tuple[np.ndarray, np.ndarray]:
    """cos δ and the shear direction t̂ of every panel at every epoch, from the normals and flow direction.

        cos δ = −n̂ · û        t̂ = (û − (û · n̂) n̂) / |û − (û · n̂) n̂|,  or 0 where that length is below
                                  SHEAR_PROJECTION_TOLERANCE (the flow along the normal)

    Parameters
    ----------
    outward_normals
        Unit normals, (N, 3) for a rigid spacecraft, or (T, N, 3) when panels move (D-88): the same code
        handles both.
    flow_direction
        û, (T, 3) unit vectors in the same frame.

    Returns
    -------
    cos_incidence : np.ndarray
        (T, N).
    shear_directions : np.ndarray
        (T, N, 3), unit vectors or zero.

    Example::

        cos_delta, shear = incidence_and_shear([[1, 0, 0]], [[-1, 0, 0]])   # [[1.]], [[[0, 0, 0]]]
    """
    # 1. Normals as (1, N, 3) or (T, N, 3), so both broadcast against û as (T, 1, 3).
    normals = np.asarray(outward_normals, dtype=float)
    if normals.ndim == 2:
        normals = normals[np.newaxis, :, :] # (1, N, 3)

    # 2. û · n̂ for every epoch and panel: (T, N), e.g. np.sum(flow[:, None, :] * normals, axis=2).
    #    cos δ is its negative.
    uhat = np.asarray(flow_direction, dtype=float)[:, np.newaxis, :] # (T, 1, 3)
    udotn = np.sum(uhat * normals, axis=2) # (T, N, 3) summed over x, y, z → (T, N)
    cos_d = -udotn
    # 3. The projection û − (û · n̂) n̂: (T, N, 3), and its length: (T, N).
    proj = uhat - udotn[..., np.newaxis] * normals  # (T, 1, 3) − (T, N, 1)·(·, N, 3) → (T, N, 3)
    # 4. t̂ = projection / length where length > SHEAR_PROJECTION_TOLERANCE, otherwise 0
    #    (np.divide with out= and where= avoids dividing by zero).
    length = np.linalg.norm(proj, axis=2)                               # (T, N)
    long_enough = length[..., np.newaxis] > SHEAR_PROJECTION_TOLERANCE  # (T, N, 1)
    t = np.divide(proj, length[..., np.newaxis], out=np.zeros_like(proj), where=long_enough)

    return cos_d, t


def _check_panel_flow_geometry(geometry: PanelFlowGeometry) -> None:
    """Raise ValueError, naming the field, if a PanelFlowGeometry is inconsistent."""
    # 1. Times, then each array's shape and finiteness.
    count = _check_times(geometry.times, geometry.time_scale, "PanelFlowGeometry")
    cos_incidence = geometry.cos_incidence
    if not isinstance(cos_incidence, np.ndarray) or cos_incidence.ndim != 2 or len(cos_incidence) != count:
        raise ValueError(
            f"PanelFlowGeometry.cos_incidence must have shape ({count}, N), got {np.shape(cos_incidence)}."
        )
    panels = cos_incidence.shape[1]
    expected = {
        "speed_m_per_s": (count,),
        "flow_direction": (count, 3),
        "cos_incidence": (count, panels),
        "shear_directions": (count, panels, 3),
    }
    for name, shape in expected.items():
        values = getattr(geometry, name)
        if not isinstance(values, np.ndarray) or values.shape != shape or not np.all(np.isfinite(values)):
            raise ValueError(
                f"PanelFlowGeometry.{name} must be finite with shape {shape}, got {np.shape(values)}."
            )

    # 2. Positive speeds, unit flow directions, cosines in [−1, 1].
    if np.any(geometry.speed_m_per_s <= 0):
        raise ValueError(
            "PanelFlowGeometry.speed_m_per_s must be positive: zero speed has no flow direction."
        )
    if np.any(np.abs(np.linalg.norm(geometry.flow_direction, axis=1) - 1) > UNIT_LENGTH_TOLERANCE):
        raise ValueError("PanelFlowGeometry.flow_direction must be unit vectors.")
    if np.any(np.abs(cos_incidence) > 1 + UNIT_LENGTH_TOLERANCE):
        raise ValueError("PanelFlowGeometry.cos_incidence must lie in [−1, 1].")

    # 3. Shear directions: unit or zero, and û · t̂ = sin δ (so t̂ points downstream along the panel).
    lengths = np.linalg.norm(geometry.shear_directions, axis=2)
    if np.any((lengths > UNIT_LENGTH_TOLERANCE) & (np.abs(lengths - 1) > UNIT_LENGTH_TOLERANCE)):
        raise ValueError("PanelFlowGeometry.shear_directions must be unit vectors or zero.")
    along = np.einsum("tk,tnk->tn", geometry.flow_direction, geometry.shear_directions)
    sin_incidence = np.sqrt(np.clip(1 - cos_incidence**2, 0, None))
    if np.any(np.abs(along - sin_incidence) > 1e-6):
        raise ValueError(
            "PanelFlowGeometry.shear_directions must be the flow direction projected onto each panel: û · t̂ "
            "should equal sin δ = √(1 − cos²δ)."
        )
    _check_source(geometry.source, "PanelFlowGeometry")


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
