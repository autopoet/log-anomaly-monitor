from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass
from datetime import datetime

from common.config import settings
from common.models import LogEvent, LogLevel, model_to_json
from common.mq import publish_json, rabbitmq_channel


@dataclass(frozen=True)
class DeviceProfile:
    device_id: str
    info_weight: int
    warn_weight: int
    error_weight: int


DEFAULT_PROFILES = [
    DeviceProfile("device_normal_01", 86, 10, 4),
    DeviceProfile("device_normal_02", 82, 13, 5),
    DeviceProfile("device_warn_01", 55, 35, 10),
    DeviceProfile("device_error_01", 30, 15, 55),
    DeviceProfile("device_flaky_01", 55, 20, 25),
]

MESSAGES = {
    LogLevel.INFO: [
        "system heartbeat is normal",
        "device metrics collected",
        "network latency is stable",
        "background task completed",
    ],
    LogLevel.WARN: [
        "cpu usage is above normal",
        "memory pressure is increasing",
        "network jitter detected",
        "retry count is rising",
    ],
    LogLevel.ERROR: [
        "service response timeout",
        "sensor data upload failed",
        "disk write operation failed",
        "device health check failed",
    ],
}


def choose_level(profile: DeviceProfile) -> LogLevel:
    return random.choices(
        [LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR],
        weights=[profile.info_weight, profile.warn_weight, profile.error_weight],
        k=1,
    )[0]


def generate_event(profile: DeviceProfile) -> LogEvent:
    level = choose_level(profile)
    return LogEvent(
        device_id=profile.device_id,
        timestamp=datetime.now(),
        log_level=level,
        message=random.choice(MESSAGES[level]),
    )


def run(node_id: str, interval_ms: int, profiles: list[DeviceProfile]) -> None:
    sleep_seconds = max(interval_ms, 1) / 1000
    with rabbitmq_channel(settings) as channel:
        print(f"[collector:{node_id}] publishing to {settings.raw_log_queue}")
        while True:
            profile = random.choice(profiles)
            event = generate_event(profile)
            publish_json(channel, settings.raw_log_queue, model_to_json(event))
            print(
                f"[collector:{node_id}] {event.timestamp.isoformat()} "
                f"{event.device_id} {event.log_level.value} {event.message}"
            )
            time.sleep(sleep_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate distributed device log producers.")
    parser.add_argument("--node-id", default="collector-01", help="collector node identifier")
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=100,
        help="message generation interval in milliseconds",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.node_id, args.interval_ms, DEFAULT_PROFILES)

