"""Tests for Epochs: UTC, GPS and SPICE ET together (task T-02, component 2).

They use a leap-second kernel holding naif0012.tls's values (``tests/conftest.py``), so they run offline.
Fixed values: GPS − UTC is TAI − UTC − 19 s (BIPM); 13 s in 1999–2005, 18 s since 2017-01-01; SPICE gives
ET = 64.18392728 s at UTC 2000-01-01T12:00:00 (32.184 s + 32 leap seconds, less 73 µs of TDB − TT).

Run: ``pytest tests/test_time_scales.py``
"""

import numpy as np
import pytest

from leodragkit import time_scales
from leodragkit.time_scales import Epochs, epochs_from_et, epochs_from_gps, epochs_from_utc


def dt(text):
    return np.datetime64(text, "ns")


@pytest.mark.parametrize(
    ("utc", "gps_minus_utc_s"),
    [("1999-06-01T00:00:00", 13), ("2016-06-01T00:00:00", 17), ("2023-10-31T13:57:18", 18)],
)
def test_gps_is_ahead_of_utc_by_tai_minus_utc_less_19_s(leap_second_kernel, utc, gps_minus_utc_s):
    epochs = epochs_from_utc([utc], leap_second_kernel)
    assert epochs.gps[0] - epochs.utc[0] == np.timedelta64(gps_minus_utc_s, "s")


def test_spire_gps_times_convert_to_utc(leap_second_kernel):
    epochs = epochs_from_gps(["2023-10-31T13:59:43", "2023-10-31T13:59:44"], leap_second_kernel)
    np.testing.assert_array_equal(epochs.utc, [dt("2023-10-31T13:59:25"), dt("2023-10-31T13:59:26")])


def test_et_at_the_j2000_epoch_matches_spice(leap_second_kernel):
    epochs = epochs_from_utc(["2000-01-01T12:00:00"], leap_second_kernel)
    assert epochs.et_s[0] == pytest.approx(64.18392728473108, abs=1e-6)


def test_et_minus_utc_in_2023_is_69_184_s_to_a_couple_of_milliseconds(leap_second_kernel):
    # 37 leap seconds + 32.184 s; TDB − TT is periodic with an amplitude of about 1.7 ms.
    epochs = epochs_from_utc(["2023-10-31T00:00:00"], leap_second_kernel)
    seconds_past_j2000 = (epochs.utc[0] - dt("2000-01-01T12:00:00")) / np.timedelta64(1, "s")
    assert epochs.et_s[0] - seconds_past_j2000 == pytest.approx(69.184, abs=2e-3)


def test_utc_gps_and_et_round_trip_to_the_nanosecond(leap_second_kernel):
    utc = np.arange(dt("2016-12-31T23:59:50"), dt("2017-01-01T00:00:10"), np.timedelta64(250, "ms"))
    from_utc = epochs_from_utc(utc, leap_second_kernel)
    np.testing.assert_array_equal(epochs_from_gps(from_utc.gps, leap_second_kernel).utc, utc)
    np.testing.assert_array_equal(epochs_from_et(from_utc.et_s, leap_second_kernel).utc, utc)


def test_the_leap_second_shows_in_gps_and_et_but_not_utc(leap_second_kernel):
    # From 23:59:59 to 00:00:00 UTC across 2017-01-01, two seconds passed: GPS and ET advance by 2 s.
    epochs = epochs_from_utc(["2016-12-31T23:59:59", "2017-01-01T00:00:00"], leap_second_kernel)
    assert np.diff(epochs.utc)[0] == np.timedelta64(1, "s")
    assert np.diff(epochs.gps)[0] == np.timedelta64(2, "s")
    assert np.diff(epochs.et_s)[0] == pytest.approx(2.0, abs=1e-6)


def test_a_gps_time_inside_a_leap_second_raises(leap_second_kernel):
    # 2016-12-31T23:59:60 UTC is 2017-01-01T00:00:17 GPS.
    with pytest.raises(ValueError, match="inside a leap second"):
        epochs_from_gps(["2017-01-01T00:00:17.5"], leap_second_kernel)
    assert epochs_from_gps(["2017-01-01T00:00:18"], leap_second_kernel).utc[0] == dt("2017-01-01T00:00:00")


@pytest.mark.parametrize("builder", [epochs_from_utc, epochs_from_gps])
def test_times_before_the_leap_second_table_raise(leap_second_kernel, builder):
    with pytest.raises(ValueError, match="before the leap-second table"):
        builder(["1971-06-01T00:00:00"], leap_second_kernel)


def test_the_kernel_is_given_to_spice_once(leap_second_kernel, monkeypatch):
    calls = []
    monkeypatch.setattr(time_scales, "_loaded_kernel_paths", set())
    monkeypatch.setattr(time_scales.spiceypy, "furnsh", lambda path: calls.append(path))
    monkeypatch.setattr(time_scales.spiceypy, "str2et", lambda strings: [0.0] * len(strings))
    for _ in range(3):
        epochs_from_utc(["2023-01-01T00:00:00"], leap_second_kernel)
    assert len(calls) == 1


def test_epochs_record_the_kernel_and_check_their_arrays(leap_second_kernel):
    epochs = epochs_from_utc(["2023-01-01T00:00:00", "2023-01-01T00:00:01"], leap_second_kernel)
    assert len(epochs) == 2 and epochs.leap_second_kernel == "test_leap_seconds.tls"
    with pytest.raises(ValueError, match="same length"):
        Epochs(utc=epochs.utc, gps=epochs.gps[:1], et_s=epochs.et_s, leap_second_kernel="k")
    with pytest.raises(ValueError, match="datetime64"):
        Epochs(utc=epochs.et_s, gps=epochs.gps, et_s=epochs.et_s, leap_second_kernel="k")


def test_bad_times_raise_naming_the_input(leap_second_kernel):
    with pytest.raises(ValueError, match="utc must be"):
        epochs_from_utc(["not a time"], leap_second_kernel)
    with pytest.raises(ValueError, match="et_s must be finite"):
        epochs_from_et([np.nan], leap_second_kernel)
