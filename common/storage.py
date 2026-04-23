from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from common.config import Settings, settings
from common.models import AlertEvent, AnalysisResult, LogEvent


@contextmanager
def connect(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path) if db_path is not None else settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(app_settings: Settings = settings) -> None:
    with connect(app_settings.sqlite_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                log_level TEXT NOT NULL,
                message TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_logs_device_time
            ON logs (device_id, timestamp);

            CREATE TABLE IF NOT EXISTS analysis_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                total_count INTEGER NOT NULL,
                warn_count INTEGER NOT NULL,
                error_count INTEGER NOT NULL,
                warn_ratio REAL NOT NULL,
                error_ratio REAL NOT NULL,
                latest_error_message TEXT,
                latest_error_timestamp TEXT,
                severe INTEGER NOT NULL,
                alert_count INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_device_time
            ON analysis_results (device_id, timestamp);

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                error_ratio REAL NOT NULL,
                window_seconds INTEGER NOT NULL,
                message TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_device_time
            ON alerts (device_id, timestamp);
            """
        )


def save_log(event: LogEvent, db_path: Path | str | None = None) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO logs (device_id, timestamp, log_level, message)
            VALUES (?, ?, ?, ?)
            """,
            (
                event.device_id,
                event.timestamp.isoformat(),
                event.log_level.value,
                event.message,
            ),
        )


def save_analysis(result: AnalysisResult, db_path: Path | str | None = None) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO analysis_results (
                device_id, timestamp, total_count, warn_count, error_count,
                warn_ratio, error_ratio, latest_error_message,
                latest_error_timestamp, severe, alert_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.device_id,
                result.timestamp.isoformat(),
                result.total_count,
                result.warn_count,
                result.error_count,
                result.warn_ratio,
                result.error_ratio,
                result.latest_error_message,
                result.latest_error_timestamp.isoformat()
                if result.latest_error_timestamp
                else None,
                int(result.severe),
                result.alert_count,
            ),
        )


def save_alert(alert: AlertEvent, db_path: Path | str | None = None) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO alerts (device_id, timestamp, error_ratio, window_seconds, message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                alert.device_id,
                alert.timestamp.isoformat(),
                alert.error_ratio,
                alert.window_seconds,
                alert.message,
            ),
        )


def list_latest_summaries(limit: int = 100, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT ar.*
            FROM analysis_results ar
            INNER JOIN (
                SELECT device_id, MAX(id) AS max_id
                FROM analysis_results
                GROUP BY device_id
            ) latest ON ar.id = latest.max_id
            ORDER BY ar.device_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_latest_summary(device_id: str, db_path: Path | str | None = None) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM analysis_results
            WHERE device_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def get_device_trend(
    device_id: str,
    limit: int = 60,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, warn_count, error_count, warn_ratio, error_ratio
            FROM analysis_results
            WHERE device_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (device_id, limit),
        ).fetchall()
        return [_row_to_dict(row) for row in reversed(rows)]


def list_alerts(limit: int = 50, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM alerts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def save_many_logs(events: Iterable[LogEvent], db_path: Path | str | None = None) -> None:
    with connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO logs (device_id, timestamp, log_level, message)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    event.device_id,
                    event.timestamp.isoformat(),
                    event.log_level.value,
                    event.message,
                )
                for event in events
            ],
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "severe" in data:
        data["severe"] = bool(data["severe"])
    return data

