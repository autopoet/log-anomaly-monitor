from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class Settings:
    rabbitmq_url: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    raw_log_queue: str = os.getenv("RAW_LOG_QUEUE", "logs.raw")
    analysis_queue: str = os.getenv("ANALYSIS_QUEUE", "logs.analysis")
    alert_queue: str = os.getenv("ALERT_QUEUE", "logs.alerts")
    window_size: int = _get_int("WINDOW_SIZE", 100)
    analysis_interval_seconds: int = _get_int("ANALYSIS_INTERVAL_SECONDS", 3)
    alert_window_seconds: int = _get_int("ALERT_WINDOW_SECONDS", 10)
    error_ratio_threshold: float = _get_float("ERROR_RATIO_THRESHOLD", 0.5)
    sqlite_path: Path = Path(os.getenv("SQLITE_PATH", "data/log_monitor.db"))


settings = Settings()

