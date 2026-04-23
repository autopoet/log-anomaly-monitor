# Requirements

## Background

Log Anomaly Monitor is a course project for a distributed log collection,
analysis, anomaly detection, and real-time visualization system. The system uses
a message-oriented middleware queue to decouple log producers from analysis and
monitoring services.

## Goals

- Simulate multiple distributed log collection nodes.
- Publish structured log events to a message queue.
- Analyze logs independently for each `device_id`.
- Maintain the latest `N` logs for each device.
- Calculate WARN and ERROR ratios.
- Track the latest ERROR event and timestamp.
- Publish periodic analysis results every configurable `T` seconds.
- Publish severe alerts when ERROR ratio exceeds a configurable threshold within
  the latest configurable `S` seconds.
- Display device status and trends in a real-time web dashboard.

## Non-Goals

- User authentication and authorization.
- Production-grade observability infrastructure.
- Real device integration.
- Kubernetes deployment.
- Complex machine learning anomaly detection.

## Log Event Format

Each collector publishes JSON messages in the following shape:

```json
{
  "device_id": "device_01",
  "timestamp": "2026-04-23 12:00:00",
  "log_level": "INFO",
  "message": "system is healthy"
}
```

Allowed `log_level` values:

- `INFO`
- `WARN`
- `ERROR`

## Functional Requirements

### Log Collection

- The system shall support multiple simulated collection nodes.
- Each node shall have a unique node identifier.
- Each node shall simulate logs from one or more devices.
- Each node shall generate one log event every 100 ms by default.
- Each log event shall be published to the raw log queue.

### Log Analysis

- The analyzer shall subscribe to all raw log events.
- The analyzer shall maintain an independent sliding window for each device.
- The sliding window size shall be configurable as `N`.
- The analyzer shall calculate:
  - ERROR ratio in the latest `N` records.
  - WARN ratio in the latest `N` records.
  - Latest ERROR event.
  - Latest ERROR timestamp.
- The analyzer shall publish analysis results every configurable `T` seconds.

### Severe Alert Detection

- The analyzer shall inspect logs in the latest configurable `S` seconds.
- If ERROR ratio in that time window is greater than the threshold, the analyzer
  shall publish a severe alert.
- The default threshold shall be `50%`.
- Alerts shall be tracked per device.

### Real-Time Monitoring

- The web service shall provide a dashboard for current device status.
- The dashboard shall show WARN and ERROR ratios for each device.
- The dashboard shall show the latest ERROR message and timestamp.
- The dashboard shall show severe alert status and alert count.
- The dashboard shall show WARN and ERROR trend lines over time.
- The dashboard shall update in real time through WebSocket.

## Configuration

The following settings should be configurable through environment variables:

| Name | Default | Description |
| --- | --- | --- |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection URL |
| `RAW_LOG_QUEUE` | `logs.raw` | Raw log queue name |
| `ANALYSIS_QUEUE` | `logs.analysis` | Analysis result queue name |
| `ALERT_QUEUE` | `logs.alerts` | Alert queue name |
| `WINDOW_SIZE` | `100` | Latest log count per device |
| `ANALYSIS_INTERVAL_SECONDS` | `3` | Analysis publishing interval |
| `ALERT_WINDOW_SECONDS` | `10` | Severe alert detection time window |
| `ERROR_RATIO_THRESHOLD` | `0.5` | Severe alert ERROR ratio threshold |
| `SQLITE_PATH` | `data/log_monitor.db` | SQLite database path |

## Quality Requirements

- The project should be easy to run locally.
- The message queue should be started with Docker Compose.
- The code should keep business logic testable without requiring RabbitMQ.
- The README should explain architecture, startup commands, and message format.
- The implementation should avoid over-engineering while keeping clear module
  boundaries.

