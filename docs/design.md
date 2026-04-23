# System Design

## Overview

Log Anomaly Monitor is organized as four cooperating parts:

1. Collectors simulate distributed log collection nodes.
2. RabbitMQ decouples producers, analysis, and monitoring.
3. The analyzer calculates per-device statistics and alerts.
4. The web service provides APIs and a real-time dashboard.

```text
+----------------+       +----------------+       +----------------+
| collector node | ----> | RabbitMQ       | ----> | analyzer       |
| producer.py    |       | logs.raw       |       | consumer.py    |
+----------------+       +----------------+       +-------+--------+
                                                          |
                                                          v
                         +----------------+       +----------------+
                         | SQLite         | <---- | analysis/alert |
                         | log_monitor.db |       | persistence    |
                         +-------+--------+       +-------+--------+
                                 ^                        |
                                 |                        v
                         +-------+--------+       +----------------+
                         | FastAPI web    | <---- | RabbitMQ       |
                         | dashboard      |       | logs.analysis  |
                         +----------------+       | logs.alerts    |
                                                  +----------------+
```

## Message Queues

| Queue | Producer | Consumer | Purpose |
| --- | --- | --- | --- |
| `logs.raw` | Collectors | Analyzer | Raw device log events |
| `logs.analysis` | Analyzer | Web service | Periodic analysis result snapshots |
| `logs.alerts` | Analyzer | Web service | Severe alert events |

Queue names are configurable to keep local experiments flexible.

## Modules

```text
collector/
  producer.py
analyzer/
  consumer.py
  detector.py
web/
  main.py
  static/
common/
  config.py
  models.py
  mq.py
  storage.py
docs/
tests/
```

### `collector`

The collector simulates multiple devices and publishes JSON log events. It can
be started multiple times with different node names to represent distributed log
collection nodes.

### `analyzer`

The analyzer consumes `logs.raw`, updates in-memory device windows, persists raw
logs to SQLite, and periodically publishes analysis snapshots. It also checks
recent time-window ERROR ratios and publishes severe alerts.

### `web`

The web service hosts static dashboard assets, exposes historical API endpoints,
and forwards live analysis and alert messages to connected WebSocket clients.

### `common`

The common package contains shared configuration, data models, RabbitMQ helpers,
and SQLite persistence code.

## Data Model

### LogEvent

| Field | Type | Description |
| --- | --- | --- |
| `device_id` | string | Device identifier |
| `timestamp` | datetime string | Event time |
| `log_level` | string | `INFO`, `WARN`, or `ERROR` |
| `message` | string | Human-readable log message |

### AnalysisResult

| Field | Type | Description |
| --- | --- | --- |
| `device_id` | string | Device identifier |
| `timestamp` | datetime string | Analysis generation time |
| `total_count` | integer | Number of logs in the count window |
| `warn_count` | integer | WARN count in the count window |
| `error_count` | integer | ERROR count in the count window |
| `warn_ratio` | number | WARN count divided by total count |
| `error_ratio` | number | ERROR count divided by total count |
| `latest_error_message` | string or null | Latest ERROR message |
| `latest_error_timestamp` | datetime string or null | Latest ERROR time |
| `severe` | boolean | Current severe alert status |
| `alert_count` | integer | Total alerts for the device |

### AlertEvent

| Field | Type | Description |
| --- | --- | --- |
| `device_id` | string | Device identifier |
| `timestamp` | datetime string | Alert time |
| `error_ratio` | number | ERROR ratio in the alert window |
| `window_seconds` | integer | Detection window size |
| `message` | string | Alert description |

## Anomaly Detection

The analyzer keeps two views per device:

- Count window: latest `N` log events.
- Time window: events whose timestamp is within the latest `S` seconds.

Periodic analysis uses the count window. Severe alert detection uses the time
window. A severe alert is emitted when:

```text
error_count_in_time_window / total_count_in_time_window > threshold
```

The default threshold is `0.5`.

To avoid repeated alert flooding, the analyzer records whether a device is
already in severe state and only emits a new alert when it transitions from
normal to severe.

## Persistence

SQLite is used for lightweight local persistence:

- `logs`: raw log events.
- `analysis_results`: periodic analysis snapshots.
- `alerts`: severe alert events.

This keeps the dashboard useful after refresh and supports simple trend queries.

## API Design

| Endpoint | Description |
| --- | --- |
| `GET /` | Dashboard page |
| `GET /api/devices` | List known devices and latest summaries |
| `GET /api/devices/{device_id}/summary` | Latest summary for one device |
| `GET /api/devices/{device_id}/trend` | Recent WARN and ERROR trend |
| `GET /api/alerts` | Recent severe alerts |
| `WS /ws/monitor` | Live analysis and alert stream |

## Runtime Flow

1. RabbitMQ starts from Docker Compose.
2. The analyzer starts and declares required queues.
3. The web service starts and declares queues used for live updates.
4. One or more collectors start and publish raw logs.
5. The analyzer consumes raw logs and updates per-device state.
6. Every `T` seconds, the analyzer publishes analysis results.
7. Severe state transitions publish alert events.
8. The web service broadcasts live messages to WebSocket clients.

## Edge Cases

- Empty device window returns zero counts and zero ratios.
- Unknown devices are ignored by per-device endpoints with a 404 response.
- Malformed queue messages are rejected after logging the error.
- Log timestamps are generated in local time but stored as ISO strings.
- Multiple devices are isolated by `device_id` so one noisy device does not
  affect other devices.

