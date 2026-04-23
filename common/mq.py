from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Iterator

import pika

from common.config import Settings, settings


@contextmanager
def rabbitmq_channel(app_settings: Settings = settings) -> Iterator[pika.adapters.blocking_connection.BlockingChannel]:
    parameters = pika.URLParameters(app_settings.rabbitmq_url)
    connection = pika.BlockingConnection(parameters)
    try:
        channel = connection.channel()
        declare_queues(channel, app_settings)
        yield channel
    finally:
        if connection.is_open:
            connection.close()


def declare_queues(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    app_settings: Settings = settings,
) -> None:
    for queue_name in (
        app_settings.raw_log_queue,
        app_settings.analysis_queue,
        app_settings.alert_queue,
    ):
        channel.queue_declare(queue=queue_name, durable=True)


def publish_json(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    queue_name: str,
    payload: str,
) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=payload.encode("utf-8"),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
        ),
    )


def consume_queue(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    queue_name: str,
    callback: Callable[[bytes], None],
) -> None:
    channel.basic_qos(prefetch_count=50)

    def _on_message(channel, method, properties, body) -> None:  # noqa: ANN001
        try:
            callback(body)
        except Exception:
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            raise
        else:
            channel.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=queue_name, on_message_callback=_on_message)
    channel.start_consuming()

