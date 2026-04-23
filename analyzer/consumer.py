from __future__ import annotations

import argparse
import logging
import threading
import time

from pydantic import ValidationError

from analyzer.detector import LogAnomalyDetector
from common.config import settings
from common.models import AlertEvent, AnalysisResult, LogEvent, model_to_json, parse_model
from common.mq import consume_queue, publish_json, rabbitmq_channel
from common.storage import init_db, save_alert, save_analysis, save_log

LOGGER = logging.getLogger(__name__)


class AnalyzerService:
    def __init__(self) -> None:
        self.detector = LogAnomalyDetector(settings)
        self._lock = threading.Lock()

    def handle_message(self, body: bytes) -> None:
        try:
            event = parse_model(LogEvent, body)
        except ValidationError:
            LOGGER.exception("invalid log event payload")
            return

        assert isinstance(event, LogEvent)
        with self._lock:
            alert = self.detector.add_event(event)

        save_log(event, settings.sqlite_path)
        if alert:
            self.publish_alert(alert)

    def publish_periodic_results(self) -> None:
        while True:
            time.sleep(settings.analysis_interval_seconds)
            with self._lock:
                results = self.detector.build_results()

            for result in results:
                save_analysis(result, settings.sqlite_path)
                self.publish_analysis(result)

            if results:
                LOGGER.info("published %s analysis result(s)", len(results))

    def publish_analysis(self, result: AnalysisResult) -> None:
        with rabbitmq_channel(settings) as channel:
            publish_json(channel, settings.analysis_queue, model_to_json(result))

    def publish_alert(self, alert: AlertEvent) -> None:
        save_alert(alert, settings.sqlite_path)
        with rabbitmq_channel(settings) as channel:
            publish_json(channel, settings.alert_queue, model_to_json(alert))
        LOGGER.warning("severe alert: %s %s", alert.device_id, alert.message)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db(settings)
    service = AnalyzerService()
    publisher = threading.Thread(target=service.publish_periodic_results, daemon=True)
    publisher.start()

    with rabbitmq_channel(settings) as channel:
        LOGGER.info("consuming %s", settings.raw_log_queue)
        consume_queue(channel, settings.raw_log_queue, service.handle_message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consume raw logs and publish analysis results.")
    return parser.parse_args()


if __name__ == "__main__":
    parse_args()
    run()

