"""Tests for the records readers return (task I1, component 1): SatelliteStates and its checks.

Run: ``pytest tests/io/test_records.py``
"""

import numpy as np
import pytest

from leodragkit.io.records import SatelliteStates, input_record_for
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
