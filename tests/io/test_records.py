"""Tests for the records readers return: SatelliteStates (I1), AttitudeRecords and keep_observed (I2).

Run: ``pytest tests/io/test_records.py``
"""

import warnings

import numpy as np
import pytest

from leodragkit.io.records import (
    AttitudeRecords,
    SatelliteStates,
    UnobservedAttitudeWarning,
    input_record_for,
    keep_observed,
)
from leodragkit.time_scales import epochs_from_gps


@pytest.fixture
def three_states(tmp_path, leap_second_kernel):
    """The arguments for a valid three-epoch SatelliteStates, as a dict to change one at a time."""
    source = tmp_path / "orbit.sp3"
    source.write_bytes(b"stand-in for a file\n")
    return {
        "epochs": epochs_from_gps(
            ["2023-10-31T13:59:40", "2023-10-31T13:59:50", "2023-10-31T14:00:00"], leap_second_kernel
        ),
        "positions_m": np.array([[6.9e6, 0.0, 0.0], [6.9e6, 7.6e4, 0.0], [6.9e6, 1.52e5, 0.0]]),
        "velocities_m_per_s": np.array([[0.0, 7.6e3, 0.0]] * 3),
        "frame": "ITRF",
        "frame_as_written": "IGS14",
        "satellite_id": "L48",
        "dropped_record_lines": (),
        "input_record": input_record_for(source),
    }


def test_valid_states_are_built(three_states):
    states = SatelliteStates(**three_states)
    assert len(states) == 3 and states.frame == "ITRF" and states.frame_as_written == "IGS14"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("positions_m", np.zeros((2, 3)), "positions_m must have shape \\(3, 3\\)"),
        ("velocities_m_per_s", np.full((3, 3), np.nan), "velocities_m_per_s must be finite"),
        ("frame", "IGS14", "frame must be one of"),
        ("satellite_id", "", "satellite_id must be a non-empty string"),
        ("dropped_record_lines", (12.0,), "line numbers"),
        ("input_record", "orbit.sp3", "input_record must be an InputRecord"),
    ],
)
def test_an_inconsistent_field_raises_naming_it(three_states, field, value, message):
    with pytest.raises(ValueError, match=message):
        SatelliteStates(**(three_states | {field: value}))


def test_epochs_must_be_strictly_increasing(three_states, leap_second_kernel):
    repeated = epochs_from_gps(
        ["2023-10-31T13:59:40", "2023-10-31T13:59:40", "2023-10-31T14:00:00"], leap_second_kernel
    )
    with pytest.raises(ValueError, match="strictly increasing"):
        SatelliteStates(**(three_states | {"epochs": repeated}))


# --- AttitudeRecords and keep_observed (task I2, component 1) ------------------------------------

SPIRE_FLAGS = {0: "observed", 1: "repeated", 2: "default"}  # leoAtt version 1.2


@pytest.fixture
def five_attitudes(tmp_path, leap_second_kernel):
    """Valid AttitudeRecords arguments: five 1 s epochs, flagged 2, 0, 1, 0, 0 (version 1.2 meanings)."""
    source = tmp_path / "attitude.log"
    source.write_bytes(b"stand-in for a file\n")
    turned = [
        -0.0040895075,
        -0.0001525936,
        -0.1268052501,
        0.9919191909,
    ]  # a Spire quaternion, about 14.6 deg of yaw
    return {
        "epochs": epochs_from_gps(
            [f"2023-12-18T09:52:{second}" for second in range(13, 18)], leap_second_kernel
        ),
        "quaternions": np.array([[0.0, 0.0, 0.0, 1.0], turned, turned, turned, turned]),
        "scalar_position": "last",
        "algebra": "hamilton",
        "direction": "body_to_reference",
        "frame": "orbit_level_spire",
        "quality_flags": np.array([2, 0, 1, 0, 0]),
        "flag_meanings": SPIRE_FLAGS,
        "satellite_id": "FM134",
        "file_version": "1.2",
        "dropped_record_lines": (),
        "input_record": input_record_for(source),
    }


def test_valid_attitude_records_are_built(five_attitudes):
    records = AttitudeRecords(**five_attitudes)
    assert len(records) == 5 and records.frame == "orbit_level_spire" and records.file_version == "1.2"


def test_keep_observed_keeps_flag_0_and_warns_with_the_counts_left_out(five_attitudes):
    records = AttitudeRecords(**five_attitudes)
    with pytest.warns(
        UnobservedAttitudeWarning,
        match="kept 3 observed attitude epochs of 5; left out repeated 1, default 1",
    ):
        observed = keep_observed(records)
    assert len(observed) == 3 and np.all(observed.quality_flags == 0)
    np.testing.assert_array_equal(observed.epochs.gps, records.epochs.gps[[1, 3, 4]])
    assert len(records) == 5  # the original is left as it was, so both can be saved


def test_keep_observed_is_silent_when_everything_was_observed(five_attitudes):
    records = AttitudeRecords(**(five_attitudes | {"quality_flags": np.zeros(5, dtype=int)}))
    with warnings.catch_warnings():
        warnings.simplefilter("error", UnobservedAttitudeWarning)
        assert len(keep_observed(records)) == 5


def test_keep_observed_raises_when_nothing_was_observed(five_attitudes):
    records = AttitudeRecords(**(five_attitudes | {"quality_flags": np.full(5, 2)}))
    with pytest.raises(ValueError, match="no attitude epoch was observed"):
        keep_observed(records)


def test_a_version_1_1_file_keeps_its_own_flag_meanings(five_attitudes):
    # Version 1.1: 0 real (observed), 1 default.
    records = AttitudeRecords(
        **(
            five_attitudes
            | {"quality_flags": np.array([1, 0, 0, 0, 0]), "flag_meanings": {0: "observed", 1: "default"}}
        )
    )
    with pytest.warns(UnobservedAttitudeWarning, match="left out default 1"):
        assert len(keep_observed(records)) == 4


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("quaternions", np.zeros((5, 3)), "quaternions must have shape \\(5, 4\\)"),
        ("quaternions", np.full((5, 4), np.nan), "quaternions must be finite"),
        ("quality_flags", np.array([0, 0, 3, 0, 0]), "flags \\[3\\] that flag_meanings does not define"),
        ("quality_flags", np.zeros(5), "quality_flags must be 5 integers"),
        ("flag_meanings", {0: "real", 1: "default"}, "the meaning 'observed'"),
        ("scalar_position", "middle", "scalar_position must be one of"),
        ("algebra", "shuster", "algebra must be one of"),
        ("direction", "body_to_orbit", "direction must be one of"),
        ("frame", "LVLH", "frame must be one of"),
        ("file_version", "", "file_version must be a non-empty string"),
    ],
)
def test_inconsistent_attitude_records_raise_naming_the_field(five_attitudes, field, value, message):
    with pytest.raises(ValueError, match=message):
        AttitudeRecords(**(five_attitudes | {field: value}))


def test_attitude_epochs_must_be_strictly_increasing(five_attitudes, leap_second_kernel):
    repeated = epochs_from_gps(["2023-12-18T09:52:13"] * 2 + ["2023-12-18T09:52:15"] * 3, leap_second_kernel)
    with pytest.raises(ValueError, match="strictly increasing"):
        AttitudeRecords(**(five_attitudes | {"epochs": repeated}))
