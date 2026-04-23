# Log Anomaly Monitor

Log Anomaly Monitor is a lightweight distributed log collection, anomaly
detection, and real-time monitoring project. It is designed for a course
experiment, but the codebase is structured like a small open-source project.

## Features

- Simulates multiple distributed log collection nodes.
- Publishes JSON log events to RabbitMQ.
- Analyzes logs independently for each `device_id`.
- Maintains the latest `N` log records per device.
- Calculates WARN and ERROR ratios.
- Records the latest ERROR event and timestamp.
- Publishes periodic analysis results to a message queue.
- Emits severe alerts when recent ERROR ratio exceeds the threshold.
- Stores raw logs, analysis snapshots, and alerts in SQLite.
- Displays device status and WARN/ERROR trends in a real-time dashboard.

## Tech Stack

- Python 3.11+
- RabbitMQ
- FastAPI
- WebSocket
- SQLite
- ECharts
- Pytest

## Architecture

```text
collectors -> RabbitMQ logs.raw -> analyzer -> RabbitMQ logs.analysis
                                      |       -> RabbitMQ logs.alerts
                                      v
                                   SQLite
                                      ^
                                      |
                                 FastAPI + WebSocket -> Dashboard
```

## Message Format

```json
{
  "device_id": "device_01",
  "timestamp": "2026-04-23 12:00:00",
  "log_level": "INFO",
  "message": "system is healthy"
}
```

Allowed `log_level` values are `INFO`, `WARN`, and `ERROR`.

## Quick Start

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start RabbitMQ:

```bash
docker compose up -d
```

RabbitMQ management UI:

```text
http://localhost:15672
guest / guest
```

Initialize and run the analyzer:

```bash
python -m analyzer.consumer
```

Start one or more collectors in separate terminals:

```bash
python -m collector.producer --node-id collector-01
python -m collector.producer --node-id collector-02
```

Start the web dashboard:

```bash
python -m uvicorn web.main:app --reload
```

Open:

```text
http://localhost:8000
```

## Configuration

Copy `.env.example` if you want to manage local settings explicitly. The project
reads these environment variables directly:

| Name | Default | Description |
| --- | --- | --- |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection URL |
| `RAW_LOG_QUEUE` | `logs.raw` | Raw log queue name |
| `ANALYSIS_QUEUE` | `logs.analysis` | Analysis result queue name |
| `ALERT_QUEUE` | `logs.alerts` | Severe alert queue name |
| `WINDOW_SIZE` | `100` | Latest log count per device |
| `ANALYSIS_INTERVAL_SECONDS` | `3` | Analysis publish interval |
| `ALERT_WINDOW_SECONDS` | `10` | Severe alert detection window |
| `ERROR_RATIO_THRESHOLD` | `0.5` | Severe alert threshold |
| `SQLITE_PATH` | `data/log_monitor.db` | SQLite database path |

## Project Structure

```text
analyzer/
  consumer.py      # RabbitMQ consumer and periodic result publisher
  detector.py      # Sliding-window statistics and alert detection
collector/
  producer.py      # Simulated distributed log collector
common/
  config.py        # Environment-based settings
  models.py        # Shared Pydantic models
  mq.py            # RabbitMQ helpers
  storage.py       # SQLite persistence and queries
docs/
  requirements.md
  design.md
web/
  main.py          # FastAPI app and WebSocket broadcast
  static/          # Dashboard assets
tests/
  test_detector.py
```

## Tests

```bash
python -m pytest
```

The current tests focus on the core detector logic:

- WARN/ERROR ratio calculation.
- Latest ERROR tracking.
- Sliding window size.
- Per-device isolation.
- Severe alert transition behavior.

## Course Report Materials

The documentation in `docs/` can be used as the basis for the experiment report:

- `docs/requirements.md`: requirement analysis.
- `docs/design.md`: system architecture and module design.

## Future Improvements

- Add HTTP log ingestion for external devices.
- Add webhook or email alert notifications.
- Export Prometheus metrics.
- Add device grouping and filtering.
- Add Dockerfiles for all Python services.
