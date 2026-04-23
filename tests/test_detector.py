from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from analyzer.detector import LogAnomalyDetector
from common.config import settings
from common.models import LogEvent, LogLevel


def make_event(device_id: str, level: LogLevel, offset_seconds: int = 0) -> LogEvent:
    return LogEvent(
        device_id=device_id,
        timestamp=datetime(2026, 4, 23, 12, 0, 0) + timedelta(seconds=offset_seconds),
        log_level=level,
        message=f"{level.value} message",
    )


def test_detector_calculates_ratios_and_latest_error() -> None:
    test_settings = replace(settings, window_size=4, alert_window_seconds=10)
    detector = LogAnomalyDetector(test_settings)

    detector.add_event(make_event("device_a", LogLevel.INFO))
    detector.add_event(make_event("device_a", LogLevel.WARN, 1))
    detector.add_event(make_event("device_a", LogLevel.ERROR, 2))
    detector.add_event(make_event("device_a", LogLevel.ERROR, 3))

    [result] = detector.build_results(datetime(2026, 4, 23, 12, 0, 4))

    assert result.device_id == "device_a"
    assert result.total_count == 4
    assert result.warn_count == 1
    assert result.error_count == 2
    assert result.warn_ratio == 0.25
    assert result.error_ratio == 0.5
    assert result.latest_error_message == "ERROR message"
    assert result.latest_error_timestamp == datetime(2026, 4, 23, 12, 0, 3)


def test_detector_keeps_latest_n_events_per_device() -> None:
    test_settings = replace(settings, window_size=3, alert_window_seconds=10)
    detector = LogAnomalyDetector(test_settings)

    detector.add_event(make_event("device_a", LogLevel.ERROR, 0))
    detector.add_event(make_event("device_a", LogLevel.INFO, 1))
    detector.add_event(make_event("device_a", LogLevel.INFO, 2))
    detector.add_event(make_event("device_a", LogLevel.WARN, 3))

    [result] = detector.build_results()

    assert result.total_count == 3
    assert result.error_count == 0
    assert result.warn_count == 1


def test_detector_isolates_devices() -> None:
    test_settings = replace(settings, window_size=10, alert_window_seconds=10)
    detector = LogAnomalyDetector(test_settings)

    detector.add_event(make_event("device_a", LogLevel.ERROR))
    detector.add_event(make_event("device_b", LogLevel.INFO))
    detector.add_event(make_event("device_b", LogLevel.WARN, 1))

    results = {result.device_id: result for result in detector.build_results()}

    assert results["device_a"].error_count == 1
    assert results["device_b"].error_count == 0
    assert results["device_b"].warn_count == 1


def test_detector_alerts_only_on_severe_transition() -> None:
    test_settings = replace(
        settings,
        window_size=10,
        alert_window_seconds=10,
        error_ratio_threshold=0.5,
    )
    detector = LogAnomalyDetector(test_settings)

    first_alert = detector.add_event(make_event("device_a", LogLevel.ERROR, 0))
    repeated_alert = detector.add_event(make_event("device_a", LogLevel.ERROR, 1))
    detector.add_event(make_event("device_a", LogLevel.INFO, 20))
    no_alert_at_equal_threshold = detector.add_event(make_event("device_a", LogLevel.ERROR, 21))
    second_alert = detector.add_event(make_event("device_a", LogLevel.ERROR, 22))

    assert first_alert is not None
    assert repeated_alert is None
    assert no_alert_at_equal_threshold is None
    assert second_alert is not None

    [result] = detector.build_results()
    assert result.alert_count == 2
    assert result.severe is True
