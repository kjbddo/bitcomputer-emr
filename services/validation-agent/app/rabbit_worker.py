"""RabbitMQ 컨슈머 (F-H7 대책).

pika `BlockingConnection` 은 사용자 콜백이 도는 동안 하트비트 프레임을 보내지
않는다. 예전 구현은 `run_validation_agent` 를 콜백 스레드에서 그대로 돌렸으므로,
작업이 하트비트 주기 두 번(=120초)을 넘기면 브로커가 연결을 닫고, 이어지는
`basic_ack` 가 실패하고, 예외가 바깥 재접속 루프로 빠져나가고, ack 되지 않은
메시지가 재전달되어 **같은 비싼 작업이 무한히 다시 돈다.** `prefetch_count=1`
이므로 뒤에 있는 모든 환자 작업이 그 뒤에서 대기하며 비용만 쌓인다.

로컬 브로커에서 재현했다(heartbeat 를 2초로 축소, 콜백 10초 블로킹):
`basic_ack` 가 `StreamLostError` 로 실패하고, 큐에 메시지가 1건 남고,
재전달 플래그가 `True` 로 돌아왔다. 재현 절차와 로그는
tests/test_rabbit_worker.py 의 모듈 docstring 에 있다.

대책:
- 무거운 작업은 워커 스레드로 넘긴다. 연결 스레드는 `process_data_events` 로
  폴링하며 하트비트를 계속 보낸다. publish/ack 는 폴링이 끝난 뒤 **연결
  스레드에서** 한다 — `BlockingConnection` 은 스레드 안전하지 않다.
- 그와 별개로 `run_validation_agent` 가 전역 예산을 갖는다(app/deadline.py).
  폴링은 연결을 살려 둘 뿐 작업을 멈추지는 못한다.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

import pika

from .agent import run_validation_agent
from .models import ValidationAgentRequest

logger = logging.getLogger("validation_agent.rabbit")

# 작업이 도는 동안 연결 스레드가 이벤트 루프를 돌리는 간격. 하트비트 주기(60s)
# 보다 충분히 짧아야 한다.
PUMP_INTERVAL_SECONDS = 1.0

JobRunner = Callable[[ValidationAgentRequest], Any]


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
        # 끄지 않는다(heartbeat=0). 폴링으로 하트비트를 보내게 됐으므로 죽은
        # 연결 탐지를 포기할 이유가 없다 — 끄는 것은 F-H7 의 "가장 단순한"
        # 대책이었지만, 그 대가로 상대가 죽어도 이 컨슈머가 모르게 된다.
        heartbeat=60,
        blocked_connection_timeout=30,
    )


def pump_until_done(
    connection: Any,
    worker: threading.Thread,
    poll_seconds: float = PUMP_INTERVAL_SECONDS,
) -> None:
    """워커가 끝날 때까지 연결 이벤트 루프를 돌린다.

    이 루프가 하트비트 프레임을 내보낸다. 워커가 끝나면 즉시 멈춘다 —
    계속 돌면 다음 메시지를 받지 못한다.
    """
    while worker.is_alive():
        try:
            connection.process_data_events(time_limit=poll_seconds)
        except Exception:  # noqa: BLE001
            # 연결이 이미 끊긴 경우다. 여기서 삼키면 아래 publish/ack 가
            # 실패하고 바깥 재접속 루프가 받는다 — 그 경로는 그대로 둔다.
            raise


def handle_delivery(
    connection: Any,
    channel: Any,
    method: Any,
    body: bytes,
    result_queue: str,
    runner: Optional[JobRunner] = None,
) -> None:
    """메시지 하나를 처리한다. 이 함수는 연결 스레드에서만 불린다.

    실행 순서가 계약이다: RUNNING publish -> 워커 스레드에서 작업 +
    하트비트 폴링 -> 결과 publish -> ack. ack 를 먼저 하면 결과를 잃고,
    ack 를 워커 스레드에서 하면 프레임이 뒤섞인다.
    """
    run = runner or run_validation_agent
    job_id = ""
    try:
        payload: Dict[str, Any] = json.loads(body.decode("utf-8"))
        job_id = str(payload.get("jobId") or "")
    except Exception as exc:  # noqa: BLE001
        # 본문 파싱 실패가 콜백 밖으로 나가면 재접속 -> 재전달 -> 같은 본문이
        # 또 실패하는 무한 루프가 된다. 여기서 정직하게 실패로 보고하고 ack 한다.
        logger.error("RabbitMQ 메시지 본문 파싱 실패 - %s: %s", type(exc).__name__, exc)
        _publish(channel, result_queue, {
            "jobId": job_id, "status": "FAILED", "error": f"본문 파싱 실패: {exc}",
        })
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    _publish(channel, result_queue, {"jobId": job_id, "status": "RUNNING"})

    outcome: Dict[str, Any] = {}

    def _work() -> None:
        try:
            request = ValidationAgentRequest(**payload)
            outcome["result"] = run(request).model_dump()
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc

    worker = threading.Thread(target=_work, name=f"validation-job-{job_id or 'unknown'}", daemon=True)
    started = time.monotonic()
    worker.start()
    pump_until_done(connection, worker)
    elapsed = time.monotonic() - started

    if "error" in outcome:
        exc = outcome["error"]
        logger.error(
            "RabbitMQ validation job failed and will be discarded - jobId=%s, "
            "elapsedSeconds=%.1f, exceptionType=%s, exceptionMessage=%s. Message is being "
            "acked and dropped (no retry, no dead-letter queue); this is a known gap to be "
            "addressed in the ValidationAgent redesign.",
            job_id, elapsed, type(exc).__name__, str(exc), exc_info=exc,
        )
        _publish(channel, result_queue, {"jobId": job_id, "status": "FAILED", "error": str(exc)})
    else:
        logger.info("RabbitMQ validation job done - jobId=%s, elapsedSeconds=%.1f", job_id, elapsed)
        _publish(channel, result_queue, {
            "jobId": job_id, "status": "DONE", "result": outcome["result"],
        })
    channel.basic_ack(delivery_tag=method.delivery_tag)


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
                handle_delivery(connection, ch, method, body, result_queue)

            channel.basic_consume(queue=request_queue, on_message_callback=callback)
            logger.info("RabbitMQ validation worker started - queue=%s", request_queue)
            channel.start_consuming()
        except Exception as exc:  # noqa: BLE001
            logger.warning("RabbitMQ worker connection failed, retrying: %s", exc)
            time.sleep(5)


def _publish(channel: Any, queue: str, message: Dict[str, Any]) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=json.dumps(message, ensure_ascii=False).encode("utf-8"),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )
