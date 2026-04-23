from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from common.config import settings
from common.models import AlertEvent, AnalysisResult, parse_model
from common.mq import consume_queue, rabbitmq_channel
from common.storage import (
    get_device_trend,
    get_latest_summary,
    init_db,
    list_alerts,
    list_latest_summaries,
)

LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Log Anomaly Monitor")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)

        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except RuntimeError:
                stale.append(websocket)

        if stale:
            async with self._lock:
                for websocket in stale:
                    self._connections.discard(websocket)


manager = ConnectionManager()
event_loop: asyncio.AbstractEventLoop | None = None


@app.on_event("startup")
async def startup() -> None:
    global event_loop
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db(settings)
    event_loop = asyncio.get_running_loop()
    threading.Thread(
        target=_consume_live_queue,
        args=(settings.analysis_queue, "analysis"),
        daemon=True,
    ).start()
    threading.Thread(
        target=_consume_live_queue,
        args=(settings.alert_queue, "alert"),
        daemon=True,
    ).start()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/devices")
async def api_devices() -> list[dict[str, Any]]:
    return list_latest_summaries()


@app.get("/api/devices/{device_id}/summary")
async def api_device_summary(device_id: str) -> dict[str, Any]:
    summary = get_latest_summary(device_id)
    if not summary:
        raise HTTPException(status_code=404, detail="device not found")
    return summary


@app.get("/api/devices/{device_id}/trend")
async def api_device_trend(device_id: str, limit: int = 60) -> list[dict[str, Any]]:
    summary = get_latest_summary(device_id)
    if not summary:
        raise HTTPException(status_code=404, detail="device not found")
    return get_device_trend(device_id, max(1, min(limit, 300)))


@app.get("/api/alerts")
async def api_alerts(limit: int = 50) -> list[dict[str, Any]]:
    return list_alerts(max(1, min(limit, 200)))


@app.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "devices": list_latest_summaries()})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


def _consume_live_queue(queue_name: str, message_type: str) -> None:
    try:
        with rabbitmq_channel(settings) as channel:
            LOGGER.info("web live consumer listening on %s", queue_name)
            consume_queue(
                channel,
                queue_name,
                lambda body: _handle_live_message(body, message_type),
            )
    except Exception:
        LOGGER.exception("live queue consumer stopped for %s", queue_name)


def _handle_live_message(body: bytes, message_type: str) -> None:
    global event_loop
    if event_loop is None:
        return

    try:
        if message_type == "analysis":
            payload = parse_model(AnalysisResult, body).model_dump(mode="json")
        else:
            payload = parse_model(AlertEvent, body).model_dump(mode="json")
    except (ValidationError, json.JSONDecodeError):
        LOGGER.exception("invalid live %s payload", message_type)
        return

    asyncio.run_coroutine_threadsafe(
        manager.broadcast({"type": message_type, "payload": payload}),
        event_loop,
    )

