"""RabbitMQ 컨슈머의 하트비트 계약 (F-H7).

**재현됨(2026-08-30, 로컬 bit-rabbitmq).** heartbeat 를 60s -> 2s 로 축소하고
동기 콜백 안에서 10초를 블로킹하자:

    [deliver #1] redelivered=False - 콜백 안에서 10s 블로킹 시작
    [deliver #1] basic_ack 실패: StreamLostError: Stream connection lost:
                 ConnectionAbortedError(10053, ...)
    [consume] start_consuming 예외로 종료: StreamLostError
    [verify] ack 되지 않고 큐에 남은 메시지 수 = 1
    [verify] 재전달 플래그 redelivered = True

pika `BlockingConnection` 은 사용자 콜백이 도는 동안 하트비트 프레임을 보내지
않는다. 콜백이 하트비트 주기 두 번을 넘기면 브로커가 연결을 닫고, 이어지는
`basic_ack` 가 실패하며, 예외가 바깥 재접속 루프로 빠져나가고, ack 되지 않은
메시지가 재전달되어 **같은 비싼 작업이 다시 돈다.** `prefetch_count=1` 이므로
뒤에 있는 모든 환자 작업이 그 뒤에서 무기한 대기한다.

대책은 두 겹이다.
1. 무거운 작업을 워커 스레드로 넘기고, 연결 스레드는 `process_data_events` 로
   폴링하며 하트비트를 계속 보낸다(이 파일).
2. `run_validation_agent` 에 전역 예산을 준다(app/deadline.py). 예산 기본값은
   브로커가 연결을 닫는 문턱(2 x heartbeat)보다 작다.

둘 다 필요하다. 1만 있으면 작업이 25분을 돌아도 아무도 멈추지 않고, 2만
있으면 예산 안의 작업도 하트비트를 놓칠 수 있다.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from app import deadline, rabbit_worker


class _FakeConnection:
    """`process_data_events` 호출 횟수와 호출 스레드를 기록하는 대역."""

    def __init__(self) -> None:
        self.pump_calls = 0
        self.pump_threads: list[str] = []

    def process_data_events(self, time_limit=0):
        self.pump_calls += 1
        self.pump_threads.append(threading.current_thread().name)
        time.sleep(min(0.02, time_limit or 0.02))


class _FakeChannel:
    def __init__(self) -> None:
        self.published: list[dict] = []
        self.acked: list[int] = []
        self.ack_threads: list[str] = []

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.published.append(json.loads(body.decode("utf-8")))

    def basic_ack(self, delivery_tag):
        self.acked.append(delivery_tag)
        self.ack_threads.append(threading.current_thread().name)


class _Method:
    delivery_tag = 7


def _body(job_id: str = "job-1") -> bytes:
    return json.dumps({"jobId": job_id, "historyId": 1}).encode("utf-8")


class _Result:
    def __init__(self, payload=None):
        self._payload = payload or {"overallStatus": "PASS", "summary": "s"}

    def model_dump(self):
        return self._payload


def test_heartbeat_pump_runs_while_the_job_is_in_flight():
    """작업이 도는 동안 연결 스레드가 하트비트를 계속 보내야 한다.

    이 폴링을 지우면(=옛 동기 콜백) 브로커가 연결을 닫는다. 위 재현 로그가
    그 결과다.
    """
    connection, channel = _FakeConnection(), _FakeChannel()

    def slow_runner(_request):
        time.sleep(0.4)
        return _Result()

    rabbit_worker.handle_delivery(
        connection, channel, _Method(), _body(), "result.q", runner=slow_runner
    )

    assert connection.pump_calls >= 2, (
        "작업이 도는 동안 하트비트를 한 번도 보내지 않았다 — F-H7 이 그대로 남아 있다"
    )


def test_job_runs_off_the_connection_thread():
    """무거운 작업이 연결 스레드를 붙잡고 있으면 하트비트를 보낼 수 없다."""
    connection, channel = _FakeConnection(), _FakeChannel()
    caller_thread = threading.current_thread().name
    seen = {}

    def runner(_request):
        seen["thread"] = threading.current_thread().name
        time.sleep(0.1)
        return _Result()

    rabbit_worker.handle_delivery(
        connection, channel, _Method(), _body(), "result.q", runner=runner
    )

    assert seen["thread"] != caller_thread


def test_ack_and_publish_happen_on_the_connection_thread():
    """pika `BlockingConnection` 은 스레드 안전하지 않다. ack/publish 를 워커
    스레드에서 하면 프레임이 뒤섞인다."""
    connection, channel = _FakeConnection(), _FakeChannel()
    caller_thread = threading.current_thread().name

    rabbit_worker.handle_delivery(
        connection, channel, _Method(), _body(), "result.q", runner=lambda _r: _Result()
    )

    assert channel.acked == [7]
    assert channel.ack_threads == [caller_thread]


def test_result_is_published_before_ack():
    connection, channel = _FakeConnection(), _FakeChannel()

    rabbit_worker.handle_delivery(
        connection, channel, _Method(), _body("job-9"), "result.q",
        runner=lambda _r: _Result({"overallStatus": "PASS"}),
    )

    statuses = [m["status"] for m in channel.published]
    assert statuses == ["RUNNING", "DONE"]
    assert channel.published[-1]["jobId"] == "job-9"
    assert channel.acked == [7]


def test_failed_job_is_reported_and_acked():
    """실패해도 ack 한다 — 재시도/DLQ 가 없는 현재 설계의 알려진 한계이며,
    ack 하지 않으면 F-H7 과 같은 무한 재처리가 된다."""
    connection, channel = _FakeConnection(), _FakeChannel()

    def exploding(_request):
        raise RuntimeError("검증 실패")

    rabbit_worker.handle_delivery(
        connection, channel, _Method(), _body(), "result.q", runner=exploding
    )

    assert [m["status"] for m in channel.published] == ["RUNNING", "FAILED"]
    assert channel.acked == [7]


def test_malformed_body_is_reported_not_crashed():
    """본문 파싱 실패가 콜백 밖으로 나가면 재접속 루프가 돌고 메시지가
    재전달된다 — 같은 본문이 다시 실패하므로 영원히 반복된다."""
    connection, channel = _FakeConnection(), _FakeChannel()

    rabbit_worker.handle_delivery(
        connection, channel, _Method(), b"{ not json", "result.q", runner=lambda _r: _Result()
    )

    assert [m["status"] for m in channel.published] == ["FAILED"]
    assert channel.acked == [7]


def test_heartbeat_stays_enabled():
    """heartbeat=0 으로 끄는 것은 즉효이지만 죽은 연결 탐지를 잃는다.

    폴링으로 하트비트를 보내게 됐으므로 끌 이유가 없다 — 끄면 이 테스트가
    실패하고, 그 트레이드오프가 의도된 것인지 다시 묻게 된다.
    """
    params = rabbit_worker._rabbit_params()
    assert params.heartbeat and params.heartbeat > 0


def test_job_budget_default_is_below_the_broker_close_threshold():
    """예산이 2 x heartbeat 를 넘으면, 폴링이 실패했을 때 곧바로 재전달 폭주다."""
    params = rabbit_worker._rabbit_params()
    assert deadline.DEFAULT_BUDGET_SECONDS < 2 * params.heartbeat


@pytest.mark.parametrize("poll", [0.05])
def test_pump_stops_when_the_worker_finishes(poll):
    """작업이 끝난 뒤에도 폴링이 계속되면 다음 메시지를 못 받는다."""
    connection = _FakeConnection()
    done = threading.Event()
    worker = threading.Thread(target=lambda: (time.sleep(0.15), done.set()), daemon=True)
    worker.start()

    rabbit_worker.pump_until_done(connection, worker, poll_seconds=poll)

    assert done.is_set()
    assert not worker.is_alive()
