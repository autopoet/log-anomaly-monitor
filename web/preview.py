from __future__ import annotations

import asyncio
import random
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from common.models import AlertEvent, AnalysisResult, LogEvent, LogLevel

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Log Anomaly Monitor Preview")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PreviewState:
    def __init__(self) -> None:
        self.devices = [
            "device_normal_01",
            "device_normal_02",
            "device_warn_01",
            "device_error_01",
            "device_flaky_01",
        ]
        self.windows: dict[str, deque[LogEvent]] = {
            device_id: deque(maxlen=60) for device_id in self.devices
        }
        self.trends: dict[str, deque[dict[str, Any]]] = {
            device_id: deque(maxlen=60) for device_id in self.devices
        }
        self.alerts: deque[dict[str, Any]] = deque(maxlen=50)
        self.alert_counts: defaultdict[str, int] = defaultdict(int)
        self.severe: defaultdict[str, bool] = defaultdict(bool)
        self.connections: set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self.lock:
            self.connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self.lock:
            connections = list(self.connections)

        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except RuntimeError:
                stale.append(websocket)

        if stale:
            async with self.lock:
                for websocket in stale:
                    self.connections.discard(websocket)


state = PreviewState()


@app.on_event("startup")
async def startup() -> None:
    for _ in range(12):
        for device_id in state.devices:
            _append_event(device_id)
    asyncio.create_task(_preview_loop())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/devices")
async def api_devices() -> list[dict[str, Any]]:
    return [_build_result(device_id).model_dump(mode="json") for device_id in state.devices]


@app.get("/api/devices/{device_id}/summary")
async def api_device_summary(device_id: str) -> dict[str, Any]:
    if device_id not in state.devices:
        raise HTTPException(status_code=404, detail="device not found")
    return _build_result(device_id).model_dump(mode="json")


@app.get("/api/devices/{device_id}/trend")
async def api_device_trend(device_id: str, limit: int = 60) -> list[dict[str, Any]]:
    if device_id not in state.devices:
        raise HTTPException(status_code=404, detail="device not found")
    rows = list(state.trends[device_id])[-max(1, min(limit, 300)) :]
    return rows


@app.get("/api/alerts")
async def api_alerts(limit: int = 50) -> list[dict[str, Any]]:
    return list(state.alerts)[: max(1, min(limit, 200))]


@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket) -> None:
    await state.connect(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "devices": await api_devices()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await state.disconnect(websocket)


async def _preview_loop() -> None:
    while True:
        await asyncio.sleep(1)
        for device_id in state.devices:
            for _ in range(random.randint(2, 5)):
                _append_event(device_id)
            result = _build_result(device_id)
            state.trends[device_id].append(
                {
                    "timestamp": result.timestamp.isoformat(),
                    "warn_count": result.warn_count,
                    "error_count": result.error_count,
                    "warn_ratio": result.warn_ratio,
                    "error_ratio": result.error_ratio,
                }
            )
            await state.broadcast({"type": "analysis", "payload": result.model_dump(mode="json")})

            alert = _maybe_build_alert(device_id, result)
            if alert:
                state.alerts.appendleft(alert.model_dump(mode="json"))
                await state.broadcast({"type": "alert", "payload": alert.model_dump(mode="json")})


def _append_event(device_id: str) -> None:
    level = random.choices(
        [LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR],
        weights=_weights_for(device_id),
        k=1,
    )[0]
    event = LogEvent(
        device_id=device_id,
        timestamp=datetime.now(),
        log_level=level,
        message=_message_for(level),
    )
    state.windows[device_id].append(event)


def _build_result(device_id: str) -> AnalysisResult:
    events = list(state.windows[device_id])
    total = len(events)
    warn_count = sum(1 for event in events if event.log_level == LogLevel.WARN)
    error_count = sum(1 for event in events if event.log_level == LogLevel.ERROR)
    latest_error = next(
        (event for event in reversed(events) if event.log_level == LogLevel.ERROR),
        None,
    )
    state.severe[device_id] = total > 0 and error_count / total > 0.5

    return AnalysisResult(
        device_id=device_id,
        timestamp=datetime.now(),
        total_count=total,
        warn_count=warn_count,
        error_count=error_count,
        warn_ratio=warn_count / total if total else 0,
        error_ratio=error_count / total if total else 0,
        latest_error_message=latest_error.message if latest_error else None,
        latest_error_timestamp=latest_error.timestamp if latest_error else None,
        severe=state.severe[device_id],
        alert_count=state.alert_counts[device_id],
    )


def _maybe_build_alert(device_id: str, result: AnalysisResult) -> AlertEvent | None:
    if not result.severe:
        return None
    if random.random() > 0.18:
        return None

    state.alert_counts[device_id] += 1
    return AlertEvent(
        device_id=device_id,
        timestamp=datetime.now(),
        error_ratio=result.error_ratio,
        window_seconds=10,
        message=f"预览数据：ERROR 占比达到 {result.error_ratio:.0%}",
    )


def _weights_for(device_id: str) -> list[int]:
    if "error" in device_id:
        return [26, 16, 58]
    if "warn" in device_id:
        return [46, 42, 12]
    if "flaky" in device_id:
        if random.random() < 0.35:
            return [22, 20, 58]
        return [62, 26, 12]
    return [84, 12, 4]


def _message_for(level: LogLevel) -> str:
    messages = {
        LogLevel.INFO: ["系统心跳正常", "设备指标采集完成", "网络延迟稳定"],
        LogLevel.WARN: ["CPU 使用率偏高", "内存压力上升", "网络抖动增加"],
        LogLevel.ERROR: ["服务响应超时", "传感器数据上传失败", "设备健康检查失败"],
    }
    return random.choice(messages[level])

