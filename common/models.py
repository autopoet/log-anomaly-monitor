from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class LogLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogEvent(BaseModel):
    device_id: str = Field(min_length=1)
    timestamp: datetime
    log_level: LogLevel
    message: str = Field(min_length=1)

    @field_validator("device_id")
    @classmethod
    def strip_device_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("device_id cannot be empty")
        return stripped


class AnalysisResult(BaseModel):
    device_id: str
    timestamp: datetime
    total_count: int
    warn_count: int
    error_count: int
    warn_ratio: float
    error_ratio: float
    latest_error_message: str | None = None
    latest_error_timestamp: datetime | None = None
    severe: bool = False
    alert_count: int = 0


class AlertEvent(BaseModel):
    device_id: str
    timestamp: datetime
    error_ratio: float
    window_seconds: int
    message: str


def model_to_json(model: BaseModel) -> str:
    return model.model_dump_json()


def parse_model(model_type: type[BaseModel], payload: bytes | str | dict[str, Any]) -> BaseModel:
    if isinstance(payload, bytes):
        return model_type.model_validate_json(payload)
    if isinstance(payload, str):
        return model_type.model_validate_json(payload)
    return model_type.model_validate(payload)

