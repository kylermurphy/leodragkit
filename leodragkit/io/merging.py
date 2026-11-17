"""Joining records of one satellite read from several files into one, and comparing them where they overlap.

Providers deliver data in pieces that overlap: Spire processes in 2-hour windows that overlap by an hour
(Spire Attitude and Navigation Product Summary, 2021, §1.2.2), so one epoch can appear in two files. These
functions work on ``io``'s record types, whatever the file format, and keep one value per epoch (D-87):

- **Orbits** (``merge_satellite_states``): from the file in which the epoch lies **furthest from either end**
  of that file's span. Orbit determination by a Kalman filter is least reliable near the ends of its arc.
- **Attitude** (``merge_attitude_records``): an **observed** value beats a repeated or default one; between
  two of the same kind, the first file in the list wins.

``overlap_differences`` reports how much overlapping files disagree (positions and velocities, or attitude
angles), and each merge summarises it in one ``RecordsMergedWarning``. ``read_sp3_files`` and
``read_spire_attitude_files`` read a list of files and merge them. Step plan: ``docs/plans/I3_merging.md``.

Read first: ``merge_satellite_states``, then ``overlap_differences`` and ``merge_attitude_records``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from leodragkit.io.records import OBSERVED, AttitudeRecords, SatelliteStates, source_names
from leodragkit.io.repeated_warnings import warn_every_time
from leodragkit.time_scales import Epochs


class RecordsMergedWarning(UserWarning):
    """Files that were merged overlapped: which value was kept, and how much the files disagreed there.

    Shown every time. To make it an error: ``warnings.simplefilter("error", RecordsMergedWarning)``.
    """


@dataclass(frozen=True)
class OverlapDifference:
    """How much two files disagree where they overlap, for one quantity."""

    first_source: str  # file names of the first record
    second_source: str
    shared_epochs: int
    quantity: str  # "position", "velocity" or "attitude angle"
    unit: str  # "m", "m/s" or "deg"
    median: float
    maximum: float


def merge_satellite_states(states_list: Sequence[SatelliteStates]) -> SatelliteStates:
    """One ``SatelliteStates`` from several of the same satellite, with one value per epoch.

    Where files overlap, each epoch's position and velocity come from the file in which it lies furthest from
    either end of that file's span (ties: the earlier file in the list). One ``RecordsMergedWarning`` names
    the overlaps and the largest differences there (``overlap_differences``).

    Raises
    ------
    ValueError
        If the list is empty, or the records differ in satellite, frame or leap-second kernel.

    Example::

        states = merge_satellite_states([read_sp3_file(path, kernel) for path in sp3_paths])
    """
    # 1. One satellite, one frame, one kernel.
    states_list = list(states_list)
    _check_same(states_list, ("satellite_id", "frame"), "SatelliteStates")
    _check_same_kernel(states_list)
    if len(states_list) == 1:
        return states_list[0]

    # 2. Every row of every file, with how central its epoch is within its file.
    rows = _rows_by_centrality(states_list)

    # 3. The chosen rows, then everything carried over.
    epochs, chosen = _chosen_epochs(states_list, rows)
    merged = SatelliteStates(
        epochs=epochs,
        positions_m=np.concatenate([states.positions_m for states in states_list])[chosen],
        velocities_m_per_s=np.concatenate([states.velocities_m_per_s for states in states_list])[chosen],
        frame=states_list[0].frame,
        frames_as_written=_unique_in_order(
            name for states in states_list for name in states.frames_as_written
        ),
        satellite_id=states_list[0].satellite_id,
        dropped_records=tuple(item for states in states_list for item in states.dropped_records),
        input_records=tuple(item for states in states_list for item in states.input_records),
    )
    _warn_about_overlaps(states_list, merged, overlap_differences(states_list))
    return merged


def merge_attitude_records(records_list: Sequence[AttitudeRecords]) -> AttitudeRecords:
    """One ``AttitudeRecords`` from several of the same satellite, with one value per epoch.

    Where files overlap, an observed value beats a repeated or default one (a gap in one file may be observed
    in another); between two of the same kind, the earlier file in the list wins. One
    ``RecordsMergedWarning`` names the overlaps, and the angle between observed values that disagree.

    Raises
    ------
    ValueError
        If the list is empty, or the records differ in satellite, frame, conventions, file version or
        leap-second kernel (flags mean different things in different versions).

    Example::

        records = merge_attitude_records([read_spire_attitude_file(path, kernel) for path in attitude_paths])
    """
    # 1. The same satellite, frame, conventions and flag meanings.
    records_list = list(records_list)
    fields = ("satellite_id", "frame", "scalar_position", "algebra", "direction", "file_version")
    _check_same(records_list, fields, "AttitudeRecords")
    _check_same_kernel(records_list)
    if len(records_list) == 1:
        return records_list[0]

    # 2. Score each row: 1 if observed, 0 if not; ties go to the earlier file.
    flags = np.concatenate([records.quality_flags for records in records_list])
    meanings = records_list[0].flag_meanings
    observed = np.array([meanings[int(flag)] == OBSERVED for flag in flags], dtype=np.int64)
    epochs, chosen = _chosen_epochs(records_list, observed)

    # 3. The chosen rows, then everything carried over.
    merged = AttitudeRecords(
        epochs=epochs,
        quaternions=np.concatenate([records.quaternions for records in records_list])[chosen],
        scalar_position=records_list[0].scalar_position,
        algebra=records_list[0].algebra,
        direction=records_list[0].direction,
        frame=records_list[0].frame,
        quality_flags=flags[chosen],
        flag_meanings=dict(meanings),
        satellite_id=records_list[0].satellite_id,
        file_version=records_list[0].file_version,
        dropped_records=tuple(item for records in records_list for item in records.dropped_records),
        input_records=tuple(item for records in records_list for item in records.input_records),
    )
    _warn_about_overlaps(records_list, merged, overlap_differences(records_list))
    return merged


def overlap_differences(records_list: Sequence[SatelliteStates | AttitudeRecords]) -> list[OverlapDifference]:
    """How much each pair of records disagrees at the epochs both hold (GPS time).

    For ``SatelliteStates``: position (m) and velocity (m/s) differences. For ``AttitudeRecords``: the angle
    (degrees) between the two attitudes, at epochs observed in both. Pairs that share no epoch are left out.

    Example::

        for difference in overlap_differences(states_list):
            print(difference.first_source, difference.second_source, difference.quantity, difference.maximum)
    """
    differences = []
    for first_index, first in enumerate(records_list):
        for second in records_list[first_index + 1 :]:
            _, in_first, in_second = np.intersect1d(first.epochs.gps, second.epochs.gps, return_indices=True)
            if isinstance(first, AttitudeRecords):
                both_observed = _observed(first)[in_first] & _observed(second)[in_second]
                in_first, in_second = in_first[both_observed], in_second[both_observed]
                if len(in_first):
                    angle = _angle_between_deg(
                        first.quaternions[in_first], second.quaternions[in_second], first
                    )
                    differences.append(_difference(first, second, "attitude angle", "deg", angle))
                continue
            if len(in_first):
                for quantity, unit, field in (
                    ("position", "m", "positions_m"),
                    ("velocity", "m/s", "velocities_m_per_s"),
                ):
                    gap = np.linalg.norm(
                        getattr(first, field)[in_first] - getattr(second, field)[in_second], axis=1
                    )
                    differences.append(_difference(first, second, quantity, unit, gap))
    return differences


def read_sp3_files(paths: Sequence[str | Path], kernel, satellite_id: str | None = None) -> SatelliteStates:
    """Read several SP3 files of one satellite and merge them (``read_sp3_file``, then
    ``merge_satellite_states``).

    Example::

        paths = sorted(Path("D:/data/spire").glob("spire_nav_L1B_leoOrb_*_FM134.sp3"))
        states = read_sp3_files(paths, kernel)
    """
    from leodragkit.io.sp3_files import read_sp3_file

    if not paths:
        raise ValueError("read_sp3_files needs at least one path.")
    return merge_satellite_states([read_sp3_file(path, kernel, satellite_id) for path in paths])


def read_spire_attitude_files(paths: Sequence[str | Path], kernel) -> AttitudeRecords:
    """Read several Spire leoAtt files of one satellite and merge them (``read_spire_attitude_file``, then
    ``merge_attitude_records``)."""
    from leodragkit.io.spire_attitude_files import read_spire_attitude_file

    if not paths:
        raise ValueError("read_spire_attitude_files needs at least one path.")
    return merge_attitude_records([read_spire_attitude_file(path, kernel) for path in paths])


def _rows_by_centrality(states_list: list[SatelliteStates]) -> np.ndarray:
    """For every row of every file: its distance (ns) to the nearer end of its own file's span."""
    distances = []
    for states in states_list:
        times = states.epochs.gps.astype(np.int64)
        distances.append(np.minimum(times - times[0], times[-1] - times))
    return np.concatenate(distances)


def _chosen_epochs(records_list, scores: np.ndarray) -> tuple[Epochs, np.ndarray]:
    """For each distinct GPS epoch, the row with the highest score (ties: the earlier file); and the merged
    Epochs, sorted by time."""
    gps = np.concatenate([records.epochs.gps for records in records_list])
    file_index = np.concatenate([np.full(len(records), index) for index, records in enumerate(records_list)])
    order = np.lexsort((file_index, -scores, gps))  # by time, then best score, then earlier file
    _, first_of_each = np.unique(gps[order], return_index=True)
    chosen = order[first_of_each]
    epochs = Epochs(
        utc=np.concatenate([records.epochs.utc for records in records_list])[chosen],
        gps=gps[chosen],
        et_s=np.concatenate([records.epochs.et_s for records in records_list])[chosen],
        leap_second_kernel=records_list[0].epochs.leap_second_kernel,
    )
    return epochs, chosen


def _warn_about_overlaps(records_list, merged, differences: list[OverlapDifference]) -> None:
    """One RecordsMergedWarning, if any epoch appeared in more than one file."""
    total = sum(len(records) for records in records_list)
    repeated = total - len(merged)
    if repeated == 0:
        return
    kept = (
        "the value from the file where each lies furthest from the ends"
        if isinstance(merged, SatelliteStates)
        else "observed values first, then the earlier file"
    )
    largest = "; ".join(
        f"{item.quantity} up to {item.maximum:.3g} {item.unit} (median {item.median:.3g})"
        for item in differences
    )
    warn_every_time(
        f"{len(records_list)} files merged into {len(merged)} epochs; {repeated} repeated epochs resolved, "
        f"keeping {kept}. Differences in overlaps: {largest or 'none compared'}.",
        RecordsMergedWarning,
        caller_depth=2,
    )


def _check_same(records_list, fields: tuple[str, ...], owner: str) -> None:
    """Raise ValueError unless the list is non-empty and every record agrees on ``fields``."""
    if not records_list:
        raise ValueError(f"Merging needs at least one {owner}.")
    for field in fields:
        values = {getattr(records, field) for records in records_list}
        if len(values) > 1:
            raise ValueError(f"Cannot merge {owner} with different {field}: {sorted(values)}.")


def _check_same_kernel(records_list) -> None:
    """Raise ValueError unless every record's epochs came from the same leap-second kernel."""
    kernels = {records.epochs.leap_second_kernel for records in records_list}
    if len(kernels) > 1:
        raise ValueError(f"Cannot merge records built with different leap-second kernels: {sorted(kernels)}.")


def _observed(records: AttitudeRecords) -> np.ndarray:
    """Which epochs' flags mean "observed"."""
    return np.array(
        [records.flag_meanings[int(flag)] == OBSERVED for flag in records.quality_flags], dtype=bool
    )


def _angle_between_deg(first: np.ndarray, second: np.ndarray, records: AttitudeRecords) -> np.ndarray:
    """The rotation angle (degrees) between two sets of quaternions written in the same conventions."""
    first_last = first[:, [1, 2, 3, 0]] if records.scalar_position == "first" else first
    second_last = second[:, [1, 2, 3, 0]] if records.scalar_position == "first" else second
    relative = Rotation.from_quat(first_last) * Rotation.from_quat(second_last).inv()
    return np.degrees(relative.magnitude())


def _difference(first, second, quantity: str, unit: str, values: np.ndarray) -> OverlapDifference:
    return OverlapDifference(
        first_source=source_names(first),
        second_source=source_names(second),
        shared_epochs=len(values),
        quantity=quantity,
        unit=unit,
        median=float(np.median(values)),
        maximum=float(np.max(values)),
    )


def _unique_in_order(names) -> tuple[str, ...]:
    """The names, without repeats, in the order first seen."""
    return tuple(dict.fromkeys(names))
