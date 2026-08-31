"""작업 전역 데드라인 (F-H7).

리뷰가 산정한 최악 시간은 25분을 넘었다: 결정 호출 4회(720s) + 처방 RAG(180s)
+ 처방 후보 조회(180s)
+ 요약(180s). 각 구간은 자기 타임아웃만 알았고 **전체 상한이 없었다.**

루프를 걷어내 결정 호출 720s 와 finder 재호출 180s 가 사라졌지만, 남은 구간만
합쳐도 여전히 500초를 넘을 수 있다. 그리고 RabbitMQ 컨슈머가 하트비트 주기
두 번(120초)을 넘기면 브로커가 연결을 닫고 메시지가 재전달되어 같은 비싼
작업이 무한히 다시 돈다. 그래서 상한은 하트비트 대책(rabbit_worker.py)과
함께 있어야 한다 — 둘 중 하나만으로는 폭주를 못 막는다.

예산이 소진되면 작업을 죽이지 않는다. 지금까지 모은 관측값으로 규칙 기반
판정을 내고, **무엇이 실행되지 않았는지 트레이스에 남긴다**(GC-2).
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

# 기본값은 RabbitMQ 하트비트 주기(60s)의 두 배 미만으로 둔다. 브로커가 연결을
# 닫는 문턱(2 x heartbeat = 120s)보다 먼저 작업이 스스로 끝나야, 워커 쪽
# 대책이 실패하더라도 재전달 폭주로 번지지 않는다.
DEFAULT_BUDGET_SECONDS = 110.0


class JobDeadline:
    """단조 시계 기준의 남은 예산.

    `time.monotonic` 을 주입받는다 — 시스템 시계 변경에 영향받지 않아야 하고,
    테스트가 시간을 통제할 수 있어야 한다.
    """

    def __init__(self, budget_seconds: float, clock: Optional[Callable[[], float]] = None) -> None:
        self._clock = clock or time.monotonic
        self._budget = max(0.0, float(budget_seconds))
        self._started = self._clock()

    @classmethod
    def from_env(cls, clock: Optional[Callable[[], float]] = None) -> "JobDeadline":
        raw = os.environ.get("VALIDATION_JOB_BUDGET_SECONDS")
        try:
            budget = float(raw) if raw is not None and raw.strip() else DEFAULT_BUDGET_SECONDS
        except ValueError:
            budget = DEFAULT_BUDGET_SECONDS
        return cls(budget, clock=clock)

    @property
    def budget_seconds(self) -> float:
        return self._budget

    def elapsed(self) -> float:
        return self._clock() - self._started

    def remaining(self) -> float:
        return self._budget - self.elapsed()

    def expired(self) -> bool:
        return self.remaining() <= 0

    def reason(self, step: str) -> str:
        return (
            f"작업 전역 예산 {self._budget:.0f}초를 초과해 '{step}' 단계를 실행하지 "
            f"않았습니다(경과 {self.elapsed():.1f}초). 지금까지 수집된 관측값만으로 "
            f"규칙 기반 판정을 냅니다."
        )
