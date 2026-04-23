from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from common.config import Settings, settings
from common.models import AlertEvent, AnalysisResult, LogEvent, LogLevel


@dataclass
class DeviceState:
    events: deque[LogEvent] = field(default_factory=deque)
    latest_error: LogEvent | None = None
    severe: bool = False
    alert_count: int = 0


class LogAnomalyDetector:
    def __init__(self, app_settings: Settings = settings):
        self.settings = app_settings
        self._devices: dict[str, DeviceState] = defaultdict(DeviceState)

    def add_event(self, event: LogEvent) -> AlertEvent | None:
        state = self._devices[event.device_id]
        state.events.append(event)

        while len(state.events) > self.settings.window_size:
            state.events.popleft()

        if event.log_level == LogLevel.ERROR:
            state.latest_error = event

        return self._check_alert(event.device_id, event.timestamp)

    def build_results(self, now: datetime | None = None) -> list[AnalysisResult]:
        timestamp = now or datetime.now()
        return [
            self._build_result(device_id, state, timestamp)
            for device_id, state in sorted(self._devices.items())
        ]

    def known_devices(self) -> list[str]:
        return sorted(self._devices.keys())

    def _build_result(
        self,
        device_id: str,
        state: DeviceState,
        timestamp: datetime,
    ) -> AnalysisResult:
        total = len(state.events)
        warn_count = sum(1 for event in state.events if event.log_level == LogLevel.WARN)
        error_count = sum(1 for event in state.events if event.log_level == LogLevel.ERROR)
        latest_error = state.latest_error

        return AnalysisResult(
            device_id=device_id,
            timestamp=timestamp,
            total_count=total,
            warn_count=warn_count,
            error_count=error_count,
            warn_ratio=warn_count / total if total else 0,
            error_ratio=error_count / total if total else 0,
            latest_error_message=latest_error.message if latest_error else None,
            latest_error_timestamp=latest_error.timestamp if latest_error else None,
            severe=state.severe,
            alert_count=state.alert_count,
        )

    def _check_alert(self, device_id: str, now: datetime) -> AlertEvent | None:
        state = self._devices[device_id]
        cutoff = now - timedelta(seconds=self.settings.alert_window_seconds)
        recent_events = [event for event in state.events if event.timestamp >= cutoff]
        total = len(recent_events)
        error_count = sum(1 for event in recent_events if event.log_level == LogLevel.ERROR)
        error_ratio = error_count / total if total else 0
        severe_now = total > 0 and error_ratio > self.settings.error_ratio_threshold

        if severe_now and not state.severe:
            state.severe = True
            state.alert_count += 1
            return AlertEvent(
                device_id=device_id,
                timestamp=now,
                error_ratio=error_ratio,
                window_seconds=self.settings.alert_window_seconds,
                message=(
                    f"ERROR ratio reached {error_ratio:.0%} in the latest "
                    f"{self.settings.alert_window_seconds} seconds"
                ),
            )

        if not severe_now:
            state.severe = False

        return None

