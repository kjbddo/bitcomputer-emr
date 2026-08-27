from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict

import pika

from .agent import run_validation_agent
from .models import ValidationAgentRequest

logger = logging.getLogger("validation_agent.rabbit")


def start_rabbit_worker_in_background() -> None:
    thread = threading.Thread(target=_consume_forever, name="validation-rabbit-worker", daemon=True)
    thread.start()


def _rabbit_params() -> pika.ConnectionParameters:
    credentials = pika.PlainCredentials(
        os.environ.get("RABBITMQ_USERNAME", "guest"),
        os.environ.get("RABBITMQ_PASSWORD", "guest"),
    )
    return pika.ConnectionParameters(
        host=os.environ.get("RABBITMQ_HOST", "rabbitmq"),
        port=int(os.environ.get("RABBITMQ_PORT", "5672")),
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )


def _consume_forever() -> None:
    request_queue = os.environ.get("VALIDATION_RABBITMQ_REQUEST_QUEUE", "validation.prescription.request")
    result_queue = os.environ.get("VALIDATION_RABBITMQ_RESULT_QUEUE", "validation.prescription.result")
    while True:
        try:
            connection = pika.BlockingConnection(_rabbit_params())
            channel = connection.channel()
            channel.queue_declare(queue=request_queue, durable=True)
            channel.queue_declare(queue=result_queue, durable=True)
            channel.basic_qos(prefetch_count=1)

            def callback(ch, method, _properties, body: bytes) -> None:
                payload: Dict[str, Any] = json.loads(body.decode("utf-8"))
                job_id = str(payload.get("jobId") or "")
                _publish(channel, result_queue, {"jobId": job_id, "status": "RUNNING"})
                try:
                    request = ValidationAgentRequest(**payload)
                    result = run_validation_agent(request).model_dump()
                    _publish(channel, result_queue, {"jobId": job_id, "status": "DONE", "result": result})
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "RabbitMQ validation job failed and will be discarded - jobId=%s, "
                        "exceptionType=%s, exceptionMessage=%s. Message is being acked and "
                        "dropped (no retry, no dead-letter queue); this is a known gap to be "
                        "addressed in the ValidationAgent redesign.",
                        job_id,
                        type(exc).__name__,
                        str(exc),
                        exc_info=True,
                    )
                    _publish(channel, result_queue, {"jobId": job_id, "status": "FAILED", "error": str(exc)})
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=request_queue, on_message_callback=callback)
            logger.info("RabbitMQ validation worker started - queue=%s", request_queue)
            channel.start_consuming()
        except Exception as exc:  # noqa: BLE001
            logger.warning("RabbitMQ worker connection failed, retrying: %s", exc)
            time.sleep(5)


def _publish(channel: pika.adapters.blocking_connection.BlockingChannel, queue: str, message: Dict[str, Any]) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=json.dumps(message, ensure_ascii=False).encode("utf-8"),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
