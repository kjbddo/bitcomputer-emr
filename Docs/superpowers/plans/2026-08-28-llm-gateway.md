# B0 — LLM 게이트웨이 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프로덕션 LLM 호출을 게이트웨이 서비스 하나로 모으고, Bedrock `bedrock-mantle` 의 `openai.gpt-5.6-luna` 로 단일화하며, LLM 을 쓰지 못한 응답이 그 사실을 드러내게 한다.

**Architecture:** `services/llm-gateway/` (FastAPI) 가 OpenAI 호환 표면을 노출하고 상류 Bedrock mantle 로 전달한다. 게이트웨이만 AWS 자격증명을 갖고, luna 의 파라미터 계약·재시도·타임아웃·계측을 소유한다. 도메인 스키마는 절대 알지 않는다. `LLM_PROVIDER=stub` 이면 서비스는 게이트웨이를 부르지 않는다.

**Tech Stack:** Python 3.11, FastAPI, httpx, pytest, LangChain(`ChatOpenAI`), Docker Compose

**Spec:** `Docs/superpowers/specs/2026-08-28-llm-gateway-design.md`

---

## Global Constraints

모든 태스크의 요구사항에 아래가 암묵적으로 포함된다.

### GC-1. 게이트웨이는 도메인 모양을 모른다

처방 JSON, 툴 결정 스키마, 진단서 텍스트 — 어떤 도메인 구조도 파싱하지 않는다. 요청 본문에서 게이트웨이가 아는 필드는 **파라미터 이름뿐**이며 값의 의미는 모른다. 이 규칙이 무너지면 게이트웨이가 두 번째 애플리케이션 계층이 된다.

### GC-2. 조용히 버리지 않는다

파라미터를 드롭하거나 변환할 때마다 기록을 남기고 계측에 포함한다. 서비스가 무시당한 것을 모른 채 디버깅하게 두지 않는다.

### GC-3. 상태는 설정이 아니라 실행 경로에서 도출한다

`llmStatus` 는 환경변수를 읽어 정하지 않는다. **LLM 응답을 실제로 받았을 때만** `real` 이다. Phase A 가 `engineStatus` 에서 정한 원칙이며, 이 계획은 그것을 LLM 경로로 확장한다.

### GC-4. stub 경로를 건드리지 않는다

`LLM_PROVIDER=stub` 일 때의 동작과 기존 stub 테스트·E2E 는 그대로 통과해야 한다. stub 은 서비스에 남고 게이트웨이를 우회한다.

### GC-5. 기존 `engineStatus` 의 의미를 바꾸지 않는다

`prescription_api` 의 `engineStatus` 는 현재 `resolve_provider()` 를 그대로 반환한다(설정 반향). 프론트가 이 값을 읽고 있을 수 있으므로 **이 계획에서는 건드리지 않는다.** `llmStatus` 를 나란히 추가한다. 이름 충돌(`xray-rag` 의 `engineStatus` 는 X-ray 엔진, `prescription` 의 것은 LLM provider) 정리는 별도 작업이다.

### GC-6. 테스트 실행

각 태스크 커밋 전 해당 서비스 디렉터리에서 `python -m pytest` 를 실행한다. 기존 통과 테스트가 깨지면 완료가 아니다.

### GC-7. 시크릿을 출력하지 않는다

Bedrock API 키를 로그·테스트 출력·커밋 어디에도 남기지 않는다. `infra/.env` 는 gitignore 상태를 유지하고 `infra/.env.example` 을 같은 커밋에서 갱신한다.

---

## File Structure

| 경로 | 책임 |
|---|---|
| `services/llm-gateway/app/config.py` | 환경변수 → 설정 객체 |
| `services/llm-gateway/app/params.py` | luna 파라미터 계약 정규화 (순수 함수) |
| `services/llm-gateway/app/upstream.py` | 상류 호출, 재시도, 타임아웃, 에러 분류 |
| `services/llm-gateway/app/metering.py` | 계측 레코드 조립 (순수 함수) |
| `services/llm-gateway/app/main.py` | FastAPI 앱, 라우트, 위 조각들의 배선 |
| `services/llm-gateway/tests/*` | 각 모듈 단위 테스트 |
| `services/llm-gateway/{Dockerfile,requirements.txt,pytest.ini}` | 패키징 |
| `infra/docker-compose.yml` | 게이트웨이 서비스 추가, 3개 서비스 환경변수 변경 |
| `services/validation-agent/app/agent.py` | 게이트웨이 경유, `llmStatus`, 폴백 트레이스 표시 |
| `services/validation-agent/app/models.py` | `llmStatus` 필드 |
| `services/prescription/prescription_api.py` | Gemini 제거, 게이트웨이 경유, `llmStatus` |
| `services/prescription/certificate_api.py` | Gemini 제거, 게이트웨이 경유, `llmStatus` |

포트: 게이트웨이는 **8003** (기존 사용: 5000 radiology, 5001 certificate, 8000 xray, 8001 prescription, 8002 validation).

---

## Task 개요

| # | 내용 | 산출물 |
|---|---|---|
| 1 | 게이트웨이 골격 + 파라미터 정규화 | `params.py`, `config.py`, 테스트 |
| 2 | 상류 호출·재시도·타임아웃·에러 분류 | `upstream.py`, 테스트 |
| 3 | 계측 | `metering.py`, 테스트 |
| 4 | FastAPI 라우트 배선 | `main.py`, 라우트 테스트 |
| 5 | 패키징·compose 편입 | Dockerfile, compose, 헬스체크 |
| 6 | validation-agent 이관 + `llmStatus` + 폴백 트레이스 | 핵심 결함 수정 |
| 7 | prescription 이관 (Gemini 제거) | |
| 8 | certificate 이관 (Gemini 제거) | |
| 9 | 실측 4항목 + spec 갱신 | 가정 제거 |
| 10 | `llmStatus` 를 Java DTO·web 까지 전달 | 결함 수정이 실제로 의사에게 도달 |

---

### Task 1: 게이트웨이 골격과 파라미터 정규화

**Files:**
- Create: `services/llm-gateway/app/__init__.py` (빈 파일)
- Create: `services/llm-gateway/app/config.py`
- Create: `services/llm-gateway/app/params.py`
- Create: `services/llm-gateway/tests/test_params.py`
- Create: `services/llm-gateway/requirements.txt`
- Create: `services/llm-gateway/pytest.ini`

**Interfaces:**
- Produces: `normalize_params(payload: dict, *, default_reasoning_effort: str) -> tuple[dict, list[str]]`
- Produces: `Settings` 데이터클래스와 `load_settings() -> Settings`

- [ ] **Step 1: 패키지 뼈대 생성**

```bash
mkdir -p services/llm-gateway/app services/llm-gateway/tests
touch services/llm-gateway/app/__init__.py
```

`services/llm-gateway/requirements.txt`:

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
pydantic>=2.6.0
httpx>=0.27.0

# 테스트
pytest>=8.0
pytest-asyncio>=0.23
```

`services/llm-gateway/pytest.ini`:

```
[pytest]
testpaths = tests
addopts = -ra --import-mode=importlib
python_files = test_*.py
pythonpath = .
asyncio_mode = auto
```

- [ ] **Step 2: 실패하는 테스트 작성**

`services/llm-gateway/tests/test_params.py`:

```python
from app.params import normalize_params


def test_temperature_removed():
    payload = {"model": "m", "messages": [], "temperature": 0.7}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert "temperature" not in result
    assert "dropped:temperature" in notes


def test_top_p_removed():
    payload = {"model": "m", "messages": [], "top_p": 0.9}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert "top_p" not in result
    assert "dropped:top_p" in notes


def test_max_tokens_renamed():
    payload = {"model": "m", "messages": [], "max_tokens": 512}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert "max_tokens" not in result
    assert result["max_completion_tokens"] == 512
    assert "renamed:max_tokens->max_completion_tokens" in notes


def test_max_tokens_dropped_when_completion_already_set():
    payload = {"model": "m", "messages": [], "max_tokens": 512, "max_completion_tokens": 256}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert result["max_completion_tokens"] == 256
    assert "max_tokens" not in result
    assert any(n.startswith("dropped:max_tokens") for n in notes)


def test_reasoning_effort_injected_when_missing():
    payload = {"model": "m", "messages": []}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert result["reasoning_effort"] == "low"
    assert "injected:reasoning_effort=low" in notes


def test_reasoning_effort_preserved_when_present():
    payload = {"model": "m", "messages": [], "reasoning_effort": "high"}
    result, notes = normalize_params(payload, default_reasoning_effort="low")
    assert result["reasoning_effort"] == "high"
    assert not any(n.startswith("injected:reasoning_effort") for n in notes)


def test_unknown_params_pass_through():
    payload = {"model": "m", "messages": [], "response_format": {"type": "json_object"}}
    result, _ = normalize_params(payload, default_reasoning_effort="low")
    assert result["response_format"] == {"type": "json_object"}


def test_input_payload_not_mutated():
    payload = {"model": "m", "messages": [], "temperature": 0.7}
    normalize_params(payload, default_reasoning_effort="low")
    assert payload["temperature"] == 0.7


def test_clean_payload_produces_no_notes_except_injection():
    payload = {"model": "m", "messages": [], "reasoning_effort": "low"}
    _, notes = normalize_params(payload, default_reasoning_effort="low")
    assert notes == []
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```bash
cd services/llm-gateway && python -m pytest tests/test_params.py -v
```

기대: `ModuleNotFoundError: No module named 'app.params'`

- [ ] **Step 4: `params.py` 구현**

`services/llm-gateway/app/params.py`:

```python
"""luna 파라미터 계약 정규화.

gpt-5.6-luna 는 이전 세대와 받는 파라미터가 다르다. 서비스(LangChain 등)가
관습적으로 보내는 필드를 여기서 한 번에 맞춘다.

게이트웨이가 아는 것은 파라미터 이름뿐이며 값의 의미는 모른다(GC-1).
드롭·변환은 반드시 기록으로 남긴다(GC-2).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# luna 가 받지 않는(또는 무시하는) 것으로 판단해 제거하는 파라미터.
# 근거와 미확인 사항은 spec §5.1 참조.
DROPPED_PARAMS = ("temperature", "top_p")


def normalize_params(
    payload: Dict[str, Any], *, default_reasoning_effort: str
) -> Tuple[Dict[str, Any], List[str]]:
    """요청 본문을 luna 계약에 맞게 정규화한다.

    입력 payload 는 변형하지 않는다.

    Returns:
        (정규화된 본문, 무엇을 드롭·변환했는지의 기록)
    """
    result = dict(payload)
    notes: List[str] = []

    for key in DROPPED_PARAMS:
        if key in result:
            result.pop(key)
            notes.append(f"dropped:{key}")

    if "max_tokens" in result:
        if "max_completion_tokens" in result:
            result.pop("max_tokens")
            notes.append("dropped:max_tokens(max_completion_tokens already set)")
        else:
            result["max_completion_tokens"] = result.pop("max_tokens")
            notes.append("renamed:max_tokens->max_completion_tokens")

    if "reasoning_effort" not in result:
        result["reasoning_effort"] = default_reasoning_effort
        notes.append(f"injected:reasoning_effort={default_reasoning_effort}")

    return result, notes
```

- [ ] **Step 5: `config.py` 구현**

`services/llm-gateway/app/config.py`:

```python
"""게이트웨이 설정.

시크릿(API 키)은 로그·에러 메시지에 절대 싣지 않는다(GC-7).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    upstream_base_url: str
    # repr=False 가 없으면 dataclass 기본 repr 이 키를 그대로 찍는다.
    # 이 객체는 요청·재시도·에러 처리 경로로 넘겨 다니도록 설계됐다(GC-7).
    api_key: str = field(repr=False)
    model: str
    reasoning_effort: str
    timeout_seconds: float
    max_retries: int
    input_price_per_1m: float
    output_price_per_1m: float


def load_settings() -> Settings:
    return Settings(
        upstream_base_url=os.environ.get(
            "LLM_UPSTREAM_BASE_URL",
            "https://bedrock-mantle.us-west-2.api.aws/openai/v1",
        ).rstrip("/"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna"),
        reasoning_effort=os.environ.get("LLM_REASONING_EFFORT", "low"),
        timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "120")),
        max_retries=int(os.environ.get("LLM_MAX_RETRIES", "2")),
        # 단가는 변동하므로 하드코딩하지 않는다. spec §7.
        input_price_per_1m=float(os.environ.get("LLM_INPUT_PRICE_PER_1M", "0.20")),
        output_price_per_1m=float(os.environ.get("LLM_OUTPUT_PRICE_PER_1M", "1.20")),
    )
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
cd services/llm-gateway && python -m pytest tests/test_params.py -v
```

기대: 9개 통과.

- [ ] **Step 7: 커밋**

```bash
git add services/llm-gateway
git commit -m "feat(llm-gateway): 파라미터 정규화와 설정 로더 추가"
```

---

### Task 2: 상류 호출과 재시도

**Files:**
- Create: `services/llm-gateway/app/upstream.py`
- Create: `services/llm-gateway/tests/test_upstream.py`

**Interfaces:**
- Consumes: Task 1 의 `Settings`
- Produces: `UpstreamError(Exception)` — 속성 `status: int | None`, `detail: str`, `attempts: int`
- Produces: `async call_upstream(client, *, url, api_key, payload, max_retries, sleep) -> tuple[dict, int]` — `(응답 JSON, 시도 횟수)`

**설계 메모:** 재시도 대기를 `sleep` 인자로 주입한다. 테스트가 실제로 잠들지 않게 하기 위한 것이며, 프로덕션에서는 `asyncio.sleep` 을 넘긴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`services/llm-gateway/tests/test_upstream.py`:

```python
import httpx
import pytest

from app.upstream import UpstreamError, call_upstream

URL = "https://upstream.test/v1/chat/completions"
PAYLOAD = {"model": "m", "messages": []}


async def _noop_sleep(_seconds: float) -> None:
    return None


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_success_first_attempt():
    def handler(_request):
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        body, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert body == {"ok": True}
    assert attempts == 1


async def test_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        body, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert body == {"ok": True}
    assert attempts == 2


async def test_retries_on_503_then_succeeds():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        _, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert attempts == 2


async def test_does_not_retry_on_400():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
            )
    assert calls["n"] == 1, "4xx 는 재시도 대상이 아니다"
    assert exc.value.status == 400
    assert exc.value.attempts == 1


async def test_gives_up_after_max_retries():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
            )
    assert calls["n"] == 3, "최초 1회 + 재시도 2회"
    assert exc.value.attempts == 3


async def test_connection_error_is_retried():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    async with _client(handler) as client:
        _, attempts = await call_upstream(
            client, url=URL, api_key="k", payload=PAYLOAD, max_retries=2, sleep=_noop_sleep
        )
    assert attempts == 2


async def test_api_key_not_in_error_detail():
    def handler(_request):
        return httpx.Response(401, text="unauthorized")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError) as exc:
            await call_upstream(
                client,
                url=URL,
                api_key="super-secret-key",
                payload=PAYLOAD,
                max_retries=0,
                sleep=_noop_sleep,
            )
    assert "super-secret-key" not in exc.value.detail
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/llm-gateway && python -m pytest tests/test_upstream.py -v
```

기대: `ModuleNotFoundError: No module named 'app.upstream'`

- [ ] **Step 3: `upstream.py` 구현**

`services/llm-gateway/app/upstream.py`:

```python
"""상류(Bedrock mantle) 호출과 재시도.

도메인 판단을 하지 않는다. 일시적 실패를 재시도하고, 끝내 실패하면
타입이 있는 에러를 올린다. 저하시킬지 실패시킬지는 서비스가 정한다(spec §6.1).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Tuple

import httpx

# 재시도해서 결과가 달라질 수 있는 상태코드만 넣는다.
# 4xx(429 제외)는 요청 자체가 잘못된 것이라 재시도해도 같다.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

SleepFn = Callable[[float], Awaitable[None]]


class UpstreamError(Exception):
    """상류 호출이 최종 실패했다."""

    def __init__(self, *, status: int | None, detail: str, attempts: int) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.attempts = attempts


def _backoff_seconds(attempt: int) -> float:
    """1회차 0.5s, 2회차 1.0s, 3회차 2.0s."""
    return 0.5 * (2 ** (attempt - 1))


async def call_upstream(
    client: httpx.AsyncClient,
    *,
    url: str,
    api_key: str,
    payload: Dict[str, Any],
    max_retries: int,
    sleep: SleepFn,
) -> Tuple[Dict[str, Any], int]:
    """상류를 호출한다.

    Returns:
        (응답 JSON, 총 시도 횟수)

    Raises:
        UpstreamError: 재시도 상한까지 실패했거나 재시도 대상이 아닌 실패.
    """
    # 헤더는 매 시도마다 새로 만든다. 에러 메시지에 절대 싣지 않는다(GC-7).
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    attempts = 0
    last_status: int | None = None
    last_detail = ""

    while True:
        attempts += 1
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            last_status = None
            last_detail = f"connection error: {type(exc).__name__}"
        else:
            if response.status_code < 400:
                try:
                    return response.json(), attempts
                except ValueError as exc:
                    # 2xx 인데 본문이 JSON 이 아니다. 여기서 그냥 터뜨리면
                    # JSONDecodeError 가 타입 없이 올라가 UpstreamError 만 잡는
                    # 호출자가 놓친다. 계약을 지키기 위해 감싼다.
                    raise UpstreamError(
                        status=response.status_code,
                        detail=(
                            f"upstream returned {response.status_code} "
                            f"with non-JSON body: {type(exc).__name__}"
                        ),
                        attempts=attempts,
                    ) from exc
            last_status = response.status_code
            last_detail = f"upstream returned {response.status_code}: {response.text[:300]}"
            if response.status_code not in RETRYABLE_STATUS:
                raise UpstreamError(status=last_status, detail=last_detail, attempts=attempts)

        if attempts > max_retries:
            raise UpstreamError(status=last_status, detail=last_detail, attempts=attempts)
        await sleep(_backoff_seconds(attempts))
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/llm-gateway && python -m pytest tests/test_upstream.py -v
```

기대: 7개 통과.

- [ ] **Step 5: 커밋**

```bash
git add services/llm-gateway
git commit -m "feat(llm-gateway): 상류 호출과 재시도·에러 분류 추가"
```

---

### Task 3: 계측

**Files:**
- Create: `services/llm-gateway/app/metering.py`
- Create: `services/llm-gateway/tests/test_metering.py`

**Interfaces:**
- Consumes: Task 1 의 `Settings`
- Produces: `build_record(*, model, caller, usage, latency_ms, attempts, outcome, param_notes, settings) -> dict`

- [ ] **Step 1: 실패하는 테스트 작성**

`services/llm-gateway/tests/test_metering.py`:

```python
from app.config import Settings
from app.metering import build_record

SETTINGS = Settings(
    upstream_base_url="https://upstream.test/v1",
    api_key="secret",
    model="openai.gpt-5.6-luna",
    reasoning_effort="low",
    timeout_seconds=120.0,
    max_retries=2,
    input_price_per_1m=0.20,
    output_price_per_1m=1.20,
)


def test_record_contains_required_fields():
    record = build_record(
        model="openai.gpt-5.6-luna",
        caller="validation-agent",
        usage={"prompt_tokens": 1000, "completion_tokens": 500},
        latency_ms=1234,
        attempts=1,
        outcome="success",
        param_notes=["dropped:temperature"],
        settings=SETTINGS,
    )
    for key in (
        "model", "caller", "inputTokens", "outputTokens",
        "latencyMs", "attempts", "outcome", "paramNotes", "estimatedCostUsd",
    ):
        assert key in record, key


def test_cost_is_computed_from_tokens_and_price():
    record = build_record(
        model="m",
        caller="c",
        usage={"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
        latency_ms=1,
        attempts=1,
        outcome="success",
        param_notes=[],
        settings=SETTINGS,
    )
    # 입력 1M × $0.20 + 출력 1M × $1.20
    assert record["estimatedCostUsd"] == 1.40


def test_missing_usage_yields_zero_tokens_not_crash():
    record = build_record(
        model="m", caller="c", usage=None, latency_ms=1, attempts=1,
        outcome="failed", param_notes=[], settings=SETTINGS,
    )
    assert record["inputTokens"] == 0
    assert record["outputTokens"] == 0
    assert record["estimatedCostUsd"] == 0.0


def test_api_key_never_appears_in_record():
    record = build_record(
        model="m", caller="c", usage={"prompt_tokens": 1, "completion_tokens": 1},
        latency_ms=1, attempts=1, outcome="success", param_notes=[], settings=SETTINGS,
    )
    assert "secret" not in str(record)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/llm-gateway && python -m pytest tests/test_metering.py -v
```

기대: `ModuleNotFoundError: No module named 'app.metering'`

- [ ] **Step 3: `metering.py` 구현**

`services/llm-gateway/app/metering.py`:

```python
"""계측 레코드 조립.

구조화 로그로 내보내 CloudWatch Logs 에서 집계한다(spec §7).
설정 객체를 받지만 단가만 읽는다 — API 키는 레코드에 절대 넣지 않는다(GC-7).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import Settings


def build_record(
    *,
    model: str,
    caller: str,
    usage: Optional[Dict[str, Any]],
    latency_ms: int,
    attempts: int,
    outcome: str,
    param_notes: List[str],
    settings: Settings,
) -> Dict[str, Any]:
    """요청 한 건의 계측 레코드를 만든다.

    outcome 은 "success" / "success_after_retry" / "failed" 중 하나다.
    """
    usage = usage or {}
    input_tokens = int(usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or 0)

    cost = (
        input_tokens / 1_000_000 * settings.input_price_per_1m
        + output_tokens / 1_000_000 * settings.output_price_per_1m
    )

    return {
        "model": model,
        "caller": caller,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "latencyMs": latency_ms,
        "attempts": attempts,
        "outcome": outcome,
        "paramNotes": param_notes,
        "estimatedCostUsd": round(cost, 6),
    }
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/llm-gateway && python -m pytest tests/test_metering.py -v
```

기대: 4개 통과.

- [ ] **Step 5: 커밋**

```bash
git add services/llm-gateway
git commit -m "feat(llm-gateway): 토큰·지연·비용 계측 레코드 추가"
```

---

### Task 4: FastAPI 라우트 배선

**Files:**
- Create: `services/llm-gateway/app/main.py`
- Create: `services/llm-gateway/tests/test_routes.py`

**Interfaces:**
- Consumes: Task 1~3 의 `load_settings`, `normalize_params`, `call_upstream`, `UpstreamError`, `build_record`
- Produces: FastAPI 앱 `app` — `POST /v1/chat/completions`, `GET /health`

**호출자 식별:** 서비스는 `X-LLM-Caller` 헤더로 자기 이름을 보낸다. 없으면 `unknown`.

- [ ] **Step 1: 실패하는 테스트 작성**

`services/llm-gateway/tests/test_routes.py`:

```python
import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture()
def client(monkeypatch):
    """상류를 MockTransport 로 바꿔치기한 앱 클라이언트."""

    def _make(handler):
        def _fake_client(**_kwargs):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(main, "make_upstream_client", _fake_client)
        return TestClient(main.app)

    return _make


def test_health_returns_ok():
    with TestClient(main.app) as c:
        response = c.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_completions_forwards_and_returns_upstream_body(client):
    def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    with client(handler) as c:
        response = c.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [], "temperature": 0.7},
            headers={"X-LLM-Caller": "validation-agent"},
        )
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "hi"


def test_temperature_is_stripped_before_upstream(client):
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"ok": True})

    with client(handler) as c:
        c.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [], "temperature": 0.7},
        )
    assert "temperature" not in seen["body"]
    assert "reasoning_effort" in seen["body"]


def test_upstream_4xx_becomes_502_without_leaking_key(client):
    def handler(_request):
        return httpx.Response(400, text="bad request")

    with client(handler) as c:
        response = c.post("/v1/chat/completions", json={"model": "m", "messages": []})
    assert response.status_code == 502
    assert "Bearer" not in response.text


def test_upstream_failure_is_logged_as_failed(client, caplog):
    def handler(_request):
        return httpx.Response(400, text="bad request")

    with client(handler) as c:
        c.post("/v1/chat/completions", json={"model": "m", "messages": []})
    assert any("failed" in rec.getMessage() for rec in caplog.records)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/llm-gateway && python -m pytest tests/test_routes.py -v
```

기대: `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: `main.py` 구현**

`services/llm-gateway/app/main.py`:

```python
"""LLM 게이트웨이.

프로덕션 서비스의 LLM 호출을 한 곳으로 모은다. 도메인 스키마를 모르며(GC-1),
파라미터 계약·재시도·계측만 소유한다. AWS 자격증명은 이 서비스에만 있다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.metering import build_record
from app.params import normalize_params
from app.upstream import UpstreamError, call_upstream

logger = logging.getLogger("llm-gateway")


def _configure_logging() -> None:
    """계측 로그가 실제로 나가게 만든다.

    설정하지 않으면 루트가 WARNING 이고 핸들러도 없다 — uvicorn 기본 설정에서도
    그렇다. 그러면 logger.info() 로 내보내는 계측 레코드가 통째로 유실된다.
    """
    # 루트가 아니라 이 로거에만 설정한다. 루트 레벨을 올리면 NOTSET 인 모든
    # 서드파티 로거의 바닥이 함께 올라가고, httpx 가 상류 호출마다 INFO 로
    # 평문 한 줄씩 찍어 "한 줄에 JSON 하나" 가 깨진다.
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    if not any(getattr(h, "_llm_gateway", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._llm_gateway = True  # type: ignore[attr-defined]
        logger.addHandler(handler)


_configure_logging()

app = FastAPI(title="LLM Gateway", version="0.1.0")

SETTINGS: Settings = load_settings()


def make_upstream_client(*, timeout: float) -> httpx.AsyncClient:
    """상류용 HTTP 클라이언트. 테스트에서 이 함수를 바꿔치기한다."""
    return httpx.AsyncClient(timeout=timeout)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    payload: Dict[str, Any] = await request.json()
    caller = request.headers.get("X-LLM-Caller", "unknown")

    normalized, param_notes = normalize_params(
        payload, default_reasoning_effort=SETTINGS.reasoning_effort
    )
    if param_notes:
        logger.warning(
            "파라미터 정규화: caller=%s notes=%s", caller, ",".join(param_notes)
        )

    url = f"{SETTINGS.upstream_base_url}/chat/completions"
    started = time.monotonic()

    async with make_upstream_client(timeout=SETTINGS.timeout_seconds) as client:
        try:
            body, attempts = await call_upstream(
                client,
                url=url,
                api_key=SETTINGS.api_key,
                payload=normalized,
                max_retries=SETTINGS.max_retries,
                sleep=asyncio.sleep,
            )
        except UpstreamError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            _log_record(
                model=str(normalized.get("model", SETTINGS.model)),
                caller=caller,
                usage=None,
                latency_ms=latency_ms,
                attempts=exc.attempts,
                outcome="failed",
                param_notes=param_notes,
            )
            # 상류 응답 본문을 그대로 흘리지 않는다. 키가 섞일 여지를 남기지 않는다(GC-7).
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "type": "upstream_error",
                        "upstreamStatus": exc.status,
                        "attempts": exc.attempts,
                    }
                },
            )

    latency_ms = int((time.monotonic() - started) * 1000)
    _log_record(
        model=str(normalized.get("model", SETTINGS.model)),
        caller=caller,
        usage=body.get("usage"),
        latency_ms=latency_ms,
        attempts=attempts,
        outcome="success" if attempts == 1 else "success_after_retry",
        param_notes=param_notes,
    )
    return JSONResponse(status_code=200, content=body)


def _log_record(**kwargs: Any) -> None:
    record = build_record(settings=SETTINGS, **kwargs)
    logger.info(json.dumps(record, ensure_ascii=False))
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/llm-gateway && python -m pytest -v
```

기대: 25개 통과 (params 9 + upstream 7 + metering 4 + routes 5).

- [ ] **Step 5: 커밋**

```bash
git add services/llm-gateway
git commit -m "feat(llm-gateway): FastAPI 라우트 배선"
```

---

### Task 5: 패키징과 compose 편입

**Files:**
- Create: `services/llm-gateway/Dockerfile`
- Modify: `infra/docker-compose.yml`
- Modify: `infra/.env.example`

**Interfaces:**
- Produces: compose 서비스 `llm-gateway`, 컨테이너명 `bit-llm-gateway`, 포트 8003
- Produces: 다른 서비스가 쓸 내부 URL `http://llm-gateway:8003/v1`

- [ ] **Step 1: Dockerfile 작성**

`services/llm-gateway/Dockerfile`:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8003
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

- [ ] **Step 2: compose 에 서비스 추가**

`infra/docker-compose.yml` 의 `validation-agent` 블록 **앞에** 다음을 넣는다:

```yaml
  llm-gateway:
    build:
      context: ../services/llm-gateway
    container_name: bit-llm-gateway
    environment:
      # 자격증명은 이 서비스에만 존재한다(spec §3.1).
      LLM_API_KEY: ${LLM_API_KEY}
      LLM_UPSTREAM_BASE_URL: ${LLM_UPSTREAM_BASE_URL:-https://bedrock-mantle.us-west-2.api.aws/openai/v1}
      LLM_MODEL: ${LLM_MODEL:-openai.gpt-5.6-luna}
      LLM_REASONING_EFFORT: ${LLM_REASONING_EFFORT:-low}
      LLM_TIMEOUT_SECONDS: ${LLM_TIMEOUT_SECONDS:-120}
      LLM_MAX_RETRIES: ${LLM_MAX_RETRIES:-2}
      LLM_INPUT_PRICE_PER_1M: ${LLM_INPUT_PRICE_PER_1M:-0.20}
      LLM_OUTPUT_PRICE_PER_1M: ${LLM_OUTPUT_PRICE_PER_1M:-1.20}
    ports:
      - "8003:8003"
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8003/health', timeout=5)\""]
      interval: 15s
      timeout: 10s
      retries: 20
```

- [ ] **Step 3: `.env.example` 갱신**

`infra/.env.example` 에 다음을 추가한다. 노출되면 안 되는 값은 비워 둔다:

```
# ── LLM 게이트웨이 ─────────────────────────────────────────
LLM_API_KEY=
LLM_UPSTREAM_BASE_URL=https://bedrock-mantle.us-west-2.api.aws/openai/v1
LLM_MODEL=openai.gpt-5.6-luna
# none | low | medium | high | xhigh | max
LLM_REASONING_EFFORT=low
LLM_TIMEOUT_SECONDS=120
LLM_MAX_RETRIES=2
LLM_INPUT_PRICE_PER_1M=0.20
LLM_OUTPUT_PRICE_PER_1M=1.20
LLM_GATEWAY_BASE_URL=http://llm-gateway:8003/v1
```

- [ ] **Step 4: 기동 확인**

```bash
cd infra && docker compose up -d --build llm-gateway
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8003/health
```

기대: `200`

- [ ] **Step 5: 커밋**

```bash
git add services/llm-gateway/Dockerfile infra/docker-compose.yml infra/.env.example
git commit -m "feat(llm-gateway): Dockerfile 과 compose 편입"
```

---

### Task 6: validation-agent 이관과 폴백 가시화

이 태스크가 B0 의 실질 목표다(spec §1.3). 배관 이관보다 **LLM 없이 돌았다는 사실을 드러내는 것**이 핵심이다.

**Files:**
- Modify: `services/validation-agent/app/agent.py`
- Modify: `services/validation-agent/app/models.py`
- Modify: `services/validation-agent/requirements.txt` (Gemini 없음 — 변경 없을 수 있음)
- Modify: `infra/docker-compose.yml` (validation-agent 환경변수)
- Create: `services/validation-agent/tests/test_llm_status.py`

**Interfaces:**
- Consumes: Task 5 의 `http://llm-gateway:8003/v1`
- Produces: `ValidationAgentResponse.llmStatus: str` — `"real"` / `"stub"` / `"fallback"`
- Produces: `reasoningTrace` 항목의 `source: str` — `"llm"` / `"stub"` / `"fallback"`

- [ ] **Step 1: 실패하는 테스트 작성**

`services/validation-agent/tests/test_llm_status.py`:

```python
import os

from app.agent import run_validation_agent
from app.models import ValidationAgentRequest


def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[],
    )


def test_stub_provider_reports_stub(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    assert response.llmStatus == "stub"


def test_no_gateway_configured_reports_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    response = run_validation_agent(_request())
    assert response.llmStatus == "fallback"


def test_fallback_trace_entries_are_marked(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    response = run_validation_agent(_request())
    assert response.reasoningTrace, "트레이스가 비어 있으면 이 테스트가 무의미하다"
    # 폴백으로 결정된 스텝은 트레이스만 보고 구분 가능해야 한다(spec §6.3).
    assert all(entry.get("source") == "fallback" for entry in response.reasoningTrace)


def test_trace_entries_always_carry_source(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    for entry in response.reasoningTrace:
        assert "source" in entry, "source 가 없으면 출처를 구분할 수 없다"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/validation-agent && python -m pytest tests/test_llm_status.py -v
```

기대: `AttributeError` 또는 `llmStatus` 필드 없음으로 실패.

- [ ] **Step 3: 응답 모델에 `llmStatus` 추가**

`services/validation-agent/app/models.py` 의 `ValidationAgentResponse` 마지막 필드 뒤에 추가한다:

```python
    shouldBlockAutoPrescription: bool = False
    # LLM 을 실제로 썼는지. 설정이 아니라 실행 경로에서 도출한다(spec §6.2).
    llmStatus: str = "real"
```

- [ ] **Step 4: 결정 출처를 추적하도록 `agent.py` 수정**

`_create_llm()` 을 게이트웨이 경유로 바꾼다:

```python
def _create_llm() -> Optional[ChatOpenAI]:
    """게이트웨이를 통해 LLM 에 붙는다.

    자격증명은 게이트웨이가 갖는다. 이 서비스는 base_url 만 안다(spec §3.1).
    """
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        return None
    # temperature 를 넘기지 않는다 — luna 계약이며 게이트웨이가 어차피 제거한다(spec §5).
    return ChatOpenAI(
        model=os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna"),
        base_url=base_url,
        api_key="unused-gateway-handles-auth",
        default_headers={"X-LLM-Caller": "validation-agent"},
    )
```

`_decide_next_tool()` 이 결정과 함께 출처를 돌려주도록 바꾼다:

```python
def _decide_next_tool(
    state: ValidationState,
    reasoning_trace: List[Dict[str, Any]],
    pubmed_queries: List[str],
    iteration: int,
) -> Dict[str, Any]:
    """결정 dict 에 `_source` 키를 실어 돌려준다.

    `_source` 는 트레이스 표시와 llmStatus 산출에 쓰이며, 상위에서 제거된다.
    """
    if resolve_provider() == "stub":
        decision = stub_tool_decision(iteration)
        decision["_source"] = "stub"
        return decision
    if os.environ.get("LLM_GATEWAY_BASE_URL"):
        decision = _llm_tool_decision(state, reasoning_trace, pubmed_queries, iteration)
        if decision:
            decision["_source"] = "llm"
            return decision
    decision = _fallback_tool_decision(state, pubmed_queries)
    decision["_source"] = "fallback"
    return decision
```

- [ ] **Step 5: 트레이스에 출처를 싣도록 `_invoke_tool` 과 호출부 수정**

`_invoke_tool` 시그니처에 `source` 를 추가한다:

```python
def _invoke_tool(
    reasoning_trace: List[Dict[str, Any]],
    action: str,
    thought: str,
    payload: Dict[str, Any],
    tool_obj: Any,
    source: str = "llm",
) -> Dict[str, Any]:
    try:
        observation = tool_obj.invoke(payload)
    except Exception as exc:  # noqa: BLE001
        observation = {"status": "FAILED", "evidence": [str(exc)]}
    reasoning_trace.append({
        "thought": thought,
        "action": action,
        "actionInput": payload,
        "observation": observation,
        # 이 스텝이 LLM 추론에서 나왔는지 휴리스틱에서 나왔는지(spec §6.3).
        "source": source,
    })
    return observation if isinstance(observation, dict) else {"status": "UNKNOWN", "raw": observation}
```

`_execute_decided_tool` 은 `decision["_source"]` 를 받아 `_invoke_tool` 로 넘긴다. `_execute_decided_tool` 내부의 모든 `_invoke_tool(...)` 호출에 `source=source` 를 추가한다. `run_validation_agent` 안에서 `_load_pubmed_evidence` 와 `Prescription Finder` 호출처럼 결정 없이 직접 도구를 부르는 자리는 `source="rule"` 로 표기한다.

- [ ] **Step 6: `llmStatus` 를 실행 경로에서 도출**

`run_validation_agent` 의 루프에서 출처를 모으고, 결과 조립부에 반영한다.

루프 시작 전:

```python
    decision_sources: List[str] = []
```

루프 안에서 `decision` 을 얻은 직후:

```python
        decision = _decide_next_tool(state, reasoning_trace, pubmed_queries, iteration)
        source = str(decision.pop("_source", "fallback"))
        decision_sources.append(source)
```

`final_result.update({...})` 블록에 다음을 추가한다:

```python
        "llmStatus": _resolve_llm_status(decision_sources),
```

그리고 모듈에 다음 함수를 추가한다:

```python
def _resolve_llm_status(sources: List[str]) -> str:
    """실행 경로에서 llmStatus 를 도출한다(spec §6.2, GC-3).

    설정이 아니라 실제로 무엇이 결정을 내렸는지를 본다.
    LLM 이 한 번이라도 결정했으면 real, 전부 stub 이면 stub, 그 외는 fallback.
    """
    if not sources:
        return "fallback"
    if all(s == "stub" for s in sources):
        return "stub"
    if any(s == "llm" for s in sources):
        return "real"
    return "fallback"
```

- [ ] **Step 7: compose 환경변수 변경**

`infra/docker-compose.yml` 의 `validation-agent` 블록에서 `OPENAI_API_KEY` 와 `OPENAI_MODEL` 을 제거하고 다음으로 바꾼다:

```yaml
      LLM_GATEWAY_BASE_URL: http://llm-gateway:8003/v1
      LLM_MODEL: ${LLM_MODEL:-openai.gpt-5.6-luna}
```

같은 블록의 `depends_on` 에 추가한다:

```yaml
      llm-gateway:
        condition: service_healthy
```

- [ ] **Step 8: 테스트 통과 확인**

```bash
cd services/validation-agent && python -m pytest -v
```

기대: 신규 4개 포함 전부 통과. 기존 `test_smoke.py` 도 통과해야 한다(GC-4).

- [ ] **Step 9: 커밋**

```bash
git add services/validation-agent infra/docker-compose.yml
git commit -m "feat(validation-agent): 게이트웨이 경유와 폴백 가시화

LLM 없이 휴리스틱으로 돌았다는 사실이 응답에 드러나지 않아, 고정 문자열
thought 가 LLM 추론처럼 보이고 있었다. llmStatus 와 트레이스 source 로 드러낸다."
```

---

### Task 7: prescription 이관 (Gemini 제거)

**Files:**
- Modify: `services/prescription/prescription_api.py`
- Modify: `services/prescription/requirements.txt`
- Modify: `infra/docker-compose.yml` (prescription-api 환경변수)
- Create: `services/prescription/tests/test_llm_status.py`

**Interfaces:**
- Consumes: Task 5 의 게이트웨이
- Produces: `PrescriptionRecommendResponse.llmStatus: str`

**주의(GC-5):** 기존 `engineStatus` 필드는 건드리지 않는다. `llmStatus` 를 나란히 추가한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`services/prescription/tests/test_llm_status.py`:

```python
from prescription_api import PrescriptionRecommendResponse


def test_response_model_has_llm_status():
    fields = PrescriptionRecommendResponse.model_fields
    assert "llmStatus" in fields


def test_engine_status_still_present():
    """GC-5: 기존 필드의 의미를 바꾸지 않는다."""
    fields = PrescriptionRecommendResponse.model_fields
    assert "engineStatus" in fields
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/prescription && python -m pytest tests/test_llm_status.py -v
```

기대: `llmStatus` 없음으로 실패.

- [ ] **Step 3: 응답 모델에 `llmStatus` 추가**

`services/prescription/prescription_api.py` 의 `PrescriptionRecommendResponse` 에 추가한다:

```python
    engineStatus: str = "real"
    # LLM 을 실제로 썼는지. engineStatus 와 달리 실행 경로에서 도출한다(spec §6.2).
    llmStatus: str = "real"
```

- [ ] **Step 4: Gemini 경로 제거하고 게이트웨이로 교체**

`_invoke_openai_json` 을 게이트웨이 호출로 바꾼다. `https://api.openai.com/v1/chat/completions` 하드코딩과 `OPENAI_API_KEY` 확인을 제거하고, `LLM_GATEWAY_BASE_URL` 로 보낸다. `temperature` 는 보내지 않는다:

```python
def _invoke_gateway_json(system_prompt: str, user_prompt: str) -> str:
    """게이트웨이를 통해 JSON 응답을 받는다.

    자격증명은 게이트웨이가 갖는다(spec §3.1). temperature 는 보내지 않는다 —
    luna 계약이며 게이트웨이가 어차피 제거한다(spec §5).
    """
    base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
    if not base_url:
        raise HTTPException(
            status_code=503,
            detail="LLM_GATEWAY_BASE_URL 이 설정되지 않았습니다.",
        )
    payload = {
        "model": os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna"),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"X-LLM-Caller": "prescription-api"},
                json=payload,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"]).strip()
    except httpx.HTTPStatusError as exc:
        logger.exception("게이트웨이 호출 실패: status=%s", exc.response.status_code)
        raise HTTPException(
            status_code=502,
            detail=f"LLM 게이트웨이 호출 실패: status={exc.response.status_code}",
        ) from exc
    except Exception as exc:
        logger.exception("게이트웨이 호출 실패")
        raise HTTPException(status_code=502, detail=f"LLM 게이트웨이 호출 실패: {exc}") from exc
```

LLM 호출 분기(spec §1.2 의 `_is_openai_model` 분기)를 지우고 다음으로 단순화한다:

```python
        if resolve_provider() == "stub":
            raw = stub_prescription_response(effective_top_rx)
            llm_status = "stub"
            trace_tool("llm_generate", True, status="success", model="stub", temperature=0.0)
        else:
            raw = _invoke_gateway_json(SYSTEM_PRESCRIPTION, user_msg)
            llm_status = "real"
            trace_tool("llm_generate", True, status="success", model=model_id)
```

`ChatGoogleGenerativeAI` import 와 `ChatGoogleGenerativeAIError` except 절, Gemini 전용 503 특례를 모두 제거한다. 응답 조립부에 `llmStatus=llm_status` 를 추가한다.

- [ ] **Step 5: requirements 에서 Gemini 제거**

`services/prescription/requirements.txt` 에서 `langchain-google-genai>=2.0.0` 줄을 삭제한다. `certificate_api.py` 가 아직 쓰고 있으므로 **Task 8 완료 후에 지운다** — 이 단계에서는 주석으로 표시만 한다:

```
# langchain-google-genai 는 certificate_api 이관(Task 8) 후 제거한다
langchain-google-genai>=2.0.0
```

- [ ] **Step 6: compose 환경변수 변경**

`infra/docker-compose.yml` 의 `prescription-api` 블록에서 `GEMINI_API_KEY`·`GEMINI_MODEL`·`OPENAI_API_KEY`·`OPENAI_MODEL` 을 제거하고 추가한다:

```yaml
      LLM_GATEWAY_BASE_URL: http://llm-gateway:8003/v1
      LLM_MODEL: ${LLM_MODEL:-openai.gpt-5.6-luna}
```

`depends_on` 에 `llm-gateway: {condition: service_healthy}` 를 추가한다.

- [ ] **Step 7: 테스트 통과 확인**

```bash
cd services/prescription && python -m pytest -v
```

기대: 신규 2개 포함 전부 통과. 기존 `test_recommend_stub.py` 가 통과해야 한다(GC-4).

- [ ] **Step 8: 커밋**

```bash
git add services/prescription infra/docker-compose.yml
git commit -m "feat(prescription): Gemini 제거하고 게이트웨이 경유로 전환"
```

---

### Task 8: certificate 이관 (Gemini 제거)

**Files:**
- Modify: `services/prescription/certificate_api.py`
- Modify: `services/prescription/requirements.txt`
- Modify: `infra/docker-compose.yml` (certificate-api 환경변수)
- Create: `services/prescription/tests/test_certificate_llm_status.py`

**Interfaces:**
- Consumes: Task 5 의 게이트웨이
- Produces: `CertificateGenerateResponse.llmStatus: str`

- [ ] **Step 1: 실패하는 테스트 작성**

`services/prescription/tests/test_certificate_llm_status.py`:

```python
from certificate_api import CertificateGenerateResponse


def test_response_model_has_llm_status():
    assert "llmStatus" in CertificateGenerateResponse.model_fields


def test_llm_status_defaults_to_real():
    response = CertificateGenerateResponse(medicalCertificate="본문")
    assert response.llmStatus == "real"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/prescription && python -m pytest tests/test_certificate_llm_status.py -v
```

기대: `llmStatus` 없음으로 실패.

- [ ] **Step 3: 응답 모델과 호출부 수정**

`services/prescription/certificate_api.py`:

```python
class CertificateGenerateResponse(BaseModel):
    medicalCertificate: str
    # LLM 을 실제로 썼는지. 실행 경로에서 도출한다(spec §6.2).
    llmStatus: str = "real"
```

호출부를 게이트웨이로 바꾼다:

```python
    if resolve_provider() == "stub":
        certificate = stub_certificate_response(req)
        llm_status = "stub"
    else:
        base_url = os.environ.get("LLM_GATEWAY_BASE_URL")
        if not base_url:
            raise HTTPException(
                status_code=503,
                detail="LLM_GATEWAY_BASE_URL 이 설정되지 않았습니다.",
            )
        payload = {
            "model": os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna"),
            "messages": [
                {"role": "system", "content": SYSTEM_CERTIFICATE},
                {"role": "user", "content": user_msg},
            ],
        }
        timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "180"))
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"X-LLM-Caller": "certificate-api"},
                    json=payload,
                )
                response.raise_for_status()
                certificate = str(
                    response.json()["choices"][0]["message"]["content"]
                ).strip()
        except Exception as exc:
            logger.exception("게이트웨이 호출 실패 - history_id=%d", req.history_id)
            raise HTTPException(
                status_code=502, detail=f"LLM 게이트웨이 호출 실패: {exc}"
            ) from exc
        llm_status = "real"
```

반환부를 바꾼다:

```python
    return CertificateGenerateResponse(
        medicalCertificate=certificate, llmStatus=llm_status
    )
```

`ChatGoogleGenerativeAI`·`ChatGoogleGenerativeAIError` import 와 `DEFAULT_MODEL`·`DEFAULT_TEMPERATURE` 중 Gemini 전용 값들을 제거한다. `httpx` import 를 추가한다.

- [ ] **Step 4: requirements 에서 Gemini 제거**

`services/prescription/requirements.txt` 에서 Task 7 이 남긴 주석과 `langchain-google-genai>=2.0.0` 줄을 함께 삭제한다.

- [ ] **Step 5: 잔존 확인**

```bash
grep -rn "ChatGoogleGenerativeAI\|langchain_google_genai\|GEMINI_API_KEY\|GEMINI_MODEL" services/prescription/*.py services/prescription/requirements.txt
```

기대: 출력 없음 (`services/prescription/evals/` 와 `run_*.py` 는 범위 밖이므로 남아 있어도 된다).

- [ ] **Step 6: compose 환경변수 변경**

`certificate-api` 블록에서 `GEMINI_API_KEY`·`GEMINI_MODEL` 을 제거하고 `LLM_GATEWAY_BASE_URL` 과 `LLM_MODEL` 을 추가한다. `depends_on` 에 `llm-gateway` 를 추가한다.

- [ ] **Step 7: 테스트·빌드 확인**

```bash
cd services/prescription && python -m pytest -v
cd ../../infra && docker compose build certificate-api prescription-api validation-agent
```

기대: 테스트 전부 통과, 빌드 성공.

- [ ] **Step 8: 커밋**

```bash
git add services/prescription infra/docker-compose.yml
git commit -m "feat(certificate): Gemini 제거하고 게이트웨이 경유로 전환"
```

---

### Task 9: 실측과 spec 갱신

spec §10 의 네 항목은 가정이다. 실제 Bedrock mantle 을 쳐서 확인하고 결과를 문서에 남긴다. **가정으로 두면 구현 이후에 터진다.**

**Files:**
- Create: `services/llm-gateway/scripts/probe_luna.py`
- Modify: `Docs/superpowers/specs/2026-08-28-llm-gateway-design.md` (§10 결과 기록)

**전제:** `infra/.env` 에 유효한 `LLM_API_KEY` 가 있어야 한다. **키 값을 출력하거나 커밋하지 않는다(GC-7).**

- [ ] **Step 1: 실측 스크립트 작성**

`services/llm-gateway/scripts/probe_luna.py`:

```python
"""spec §10 의 실측 항목을 실제 상류에 확인한다.

키는 환경변수에서 읽고 절대 출력하지 않는다(GC-7).
게이트웨이를 거치지 않고 상류를 직접 친다 — 게이트웨이의 정규화가
결과를 가리지 않게 하기 위해서다.
"""
from __future__ import annotations

import json
import os

import httpx

BASE = os.environ.get(
    "LLM_UPSTREAM_BASE_URL", "https://bedrock-mantle.us-west-2.api.aws/openai/v1"
).rstrip("/")
KEY = os.environ["LLM_API_KEY"]
MODEL = os.environ.get("LLM_MODEL", "openai.gpt-5.6-luna")

MESSAGES = [{"role": "user", "content": "Reply with the single word: ok"}]


def probe(name: str, payload: dict) -> None:
    body = {"model": MODEL, "messages": MESSAGES, **payload}
    with httpx.Client(timeout=60) as client:
        response = client.post(
            f"{BASE}/chat/completions",
            headers={"Authorization": f"Bearer {KEY}"},
            json=body,
        )
    print(f"[{name}] status={response.status_code}")
    if response.status_code >= 400:
        print(f"  body={response.text[:300]}")


if __name__ == "__main__":
    probe("baseline", {"reasoning_effort": "low"})
    probe("with_temperature", {"reasoning_effort": "low", "temperature": 0.7})
    probe("json_object", {
        "reasoning_effort": "low",
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": 'Reply with JSON: {"ok": true}'}],
    })
    probe("tool_calling", {
        "reasoning_effort": "low",
        "tools": [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }],
        "messages": [{"role": "user", "content": "What is the weather in Seoul?"}],
    })
```

- [ ] **Step 2: 실측 실행**

```bash
set -a; . infra/.env; set +a
python services/llm-gateway/scripts/probe_luna.py
```

각 프로브의 상태코드를 기록한다. `with_temperature` 가 400 이면 luna 가 `temperature` 를 거부하는 것이고, 200 이면 무시하는 것이다.

- [ ] **Step 3: TPM 쿼터 확인**

AWS 콘솔의 Service Quotas 에서 Bedrock 의 해당 모델 TPM 기본값을 확인한다. 출력 토큰이 10배로 차감되므로, 예상 볼륨(월 입력 4M·출력 1M)을 분당으로 환산해 여유가 있는지 판단한다.

- [ ] **Step 4: spec §10 에 결과 기록**

`Docs/superpowers/specs/2026-08-28-llm-gateway-design.md` 의 §10 체크박스를 채우고, 각 항목 아래에 **관측한 상태코드와 날짜**를 적는다. `temperature` 가 거부되지 않는 것으로 밝혀지면 §5.2 의 드롭 규칙을 유지할지 재검토하고 그 판단도 적는다.

- [ ] **Step 5: 커밋**

```bash
git add services/llm-gateway/scripts Docs/superpowers/specs/2026-08-28-llm-gateway-design.md
git commit -m "test(llm-gateway): luna 파라미터 계약 실측과 spec 결과 기록"
```

---

### Task 10: llmStatus 를 UI 까지 전달

Task 6 의 `llmStatus` 는 백엔드 계약에만 존재하고 의사에게 도달하지 못한다. 리뷰어가
확인한 경로: 동기 경로에서 `ValidationEventProcessor.process` 가 응답을
`ValidationAgentResponse` DTO 로 역직렬화하는데, 이 DTO 는 `@JsonIgnoreProperties(ignoreUnknown = true)`
이면서 `llmStatus`·`reasoningTrace` 를 모른다. 그 뒤 `toJson(response)` 로 재직렬화해
`resultJson` 에 저장하므로 **두 필드가 저장 전에 사라진다.** 비동기(RabbitMQ) 경로는
`ValidationJobResultConsumer` 가 raw `Map` 을 쓰므로 살아남는다 — 즉 같은 검증이 어느
경로로 갔느냐에 따라 저장 내용이 다르다.

`apps/web` 은 `llmStatus` 를 아예 읽지 않는다. B0 의 목표(휴리스틱 출력을 모델 출력인 양
보여주는 것을 멈춘다)는 이 태스크 전까지 실제로는 달성되지 않는다.

**Files:**
- Modify: `apps/api/src/main/java/com/example/bitcomputer/model/ValidationAgentResponse.java`
- Modify: `apps/web/src/services/history.ts`
- Modify: `apps/web/src/components/Diagnosis.tsx`
- Test: `apps/api/src/test/java/com/example/bitcomputer/model/ValidationAgentResponseTest.java` (신규)
- Test: `apps/web/src/components/__tests__/Diagnosis.test.tsx` (기존이면 추가, 없으면 신규)

**Interfaces:**
- Consumes: Task 6 의 `ValidationAgentResponse.llmStatus: "real"|"stub"|"fallback"` 과
  `reasoningTrace[].source: "llm"|"stub"|"rule"|"fallback"`
- Produces: 두 필드가 동기·비동기 두 경로 모두에서 `ValidationResult.resultJson` 에 보존된다
- Produces: 검증 모달이 `llmStatus !== "real"` 일 때 모델 미사용을 명시한다

- [ ] **Step 1: 실패하는 Java 테스트 작성**

`apps/api/src/test/java/com/example/bitcomputer/model/ValidationAgentResponseTest.java`:

```java
package com.example.bitcomputer.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ValidationAgentResponseTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * ValidationEventProcessor 는 응답을 이 DTO 로 역직렬화한 뒤 다시 직렬화해
     * resultJson 에 저장한다. DTO 가 모르는 필드는 그 왕복에서 사라진다.
     * 그래서 이 테스트는 "필드가 있다"가 아니라 "왕복이 보존한다"를 단언한다.
     */
    @Test
    void roundTripPreservesLlmStatusAndReasoningTrace() throws Exception {
        String upstream = "{"
                + "\"overallStatus\": \"PASS\","
                + "\"summary\": \"이상 없음\","
                + "\"reason\": \"규칙 통과\","
                + "\"llmStatus\": \"fallback\","
                + "\"reasoningTrace\": [{\"action\": \"Disease Validator\", \"source\": \"fallback\"}],"
                + "\"recommendedPrescriptions\": [{\"name\": \"약\"}],"
                + "\"validation\": {\"k\": \"v\"}"
                + "}";

        ValidationAgentResponse parsed = objectMapper.readValue(upstream, ValidationAgentResponse.class);
        String roundTripped = objectMapper.writeValueAsString(parsed);

        assertThat(parsed.getLlmStatus()).isEqualTo("fallback");
        assertThat(roundTripped).contains("\"llmStatus\":\"fallback\"");
        assertThat(roundTripped).contains("\"source\":\"fallback\"");
        assertThat(roundTripped).contains("recommendedPrescriptions");
        assertThat(roundTripped).contains("\"reason\"");
        assertThat(roundTripped).contains("\"validation\"");
    }

    /**
     * 상류가 필드를 안 줬을 때 "모델이 돌았다"로 기울면 안 된다.
     * 파이썬 쪽 기본값과 같은 방향(fail-closed)으로 맞춘다.
     */
    @Test
    void missingLlmStatusDoesNotClaimRealModel() throws Exception {
        ValidationAgentResponse parsed = objectMapper.readValue(
                "{\"overallStatus\":\"PASS\",\"summary\":\"s\"}", ValidationAgentResponse.class);

        assertThat(parsed.getLlmStatus()).isNotEqualTo("real");
    }
}
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd apps/api && ./gradlew test --tests "*ValidationAgentResponseTest*"`
Expected: FAIL — `getLlmStatus()` 가 존재하지 않아 컴파일 에러.

- [ ] **Step 3: DTO 에 누락 필드 추가**

`ValidationAgentResponse.java` 의 필드 블록을 다음으로 교체한다. `llmStatus` 외에도
`reason`·`recommendedPrescriptions`·`validation`·`reasoningTrace` 가 같은 이유로 잘리고
있었으므로 함께 복구한다(그래야 동기·비동기 경로의 저장 내용이 같아진다):

```java
    private String overallStatus;
    private String summary;
    private String reason;
    private List<Map<String, Object>> recommendedPrescriptions;
    private Map<String, Object> validation;
    private List<Map<String, Object>> reasoningTrace;
    private List<Map<String, Object>> checks;
    private List<Map<String, Object>> suspectedIssues;
    private List<String> suggestedReviewItems;
    private List<Map<String, Object>> candidatePrescriptions;

    // 상류가 이 필드를 안 주면 "모델 미사용" 쪽으로만 틀린다.
    // 파이썬 모델도 같은 기본값이다(services/validation-agent/app/models.py).
    @Builder.Default
    private String llmStatus = "fallback";

    @JsonProperty("shouldNotifyDoctor")
    private Boolean shouldNotifyDoctor;

    @JsonProperty("shouldBlockAutoPrescription")
    private Boolean shouldBlockAutoPrescription;
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd apps/api && ./gradlew test --tests "*ValidationAgentResponseTest*"`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/model/ValidationAgentResponse.java apps/api/src/test/java/com/example/bitcomputer/model/ValidationAgentResponseTest.java
git commit -m "fix(api): 동기 검증 경로가 llmStatus 와 reasoningTrace 를 버리던 문제 수정"
```

- [ ] **Step 6: 웹 타입에 llmStatus 추가**

`apps/web/src/services/history.ts` 의 `ValidationJobResponse["result"]` 에 한 줄 추가한다.
`reasoningTrace` 는 이미 있다:

```ts
    llmStatus?: "real" | "stub" | "fallback";
```

- [ ] **Step 7: 실패하는 웹 테스트 작성**

`apps/web/src/components/__tests__/Diagnosis.test.tsx` 에 다음을 추가한다(파일이 없으면
같은 디렉터리의 다른 테스트 파일의 import 관례를 그대로 따라 새로 만든다):

```tsx
import { describe, expect, it } from "vitest";
import { llmStatusNotice } from "../Diagnosis";

describe("llmStatusNotice", () => {
  it("모델이 실제로 돌았으면 아무것도 표시하지 않는다", () => {
    expect(llmStatusNotice("real")).toBeNull();
  });

  it("폴백이면 모델 미사용을 명시한다", () => {
    const notice = llmStatusNotice("fallback");
    expect(notice).not.toBeNull();
    expect(notice!.label).toContain("모델 미사용");
    expect(notice!.tone).toBe("warning");
  });

  it("스텁이면 폴백과 구분되는 문구를 쓴다", () => {
    const stub = llmStatusNotice("stub");
    const fallback = llmStatusNotice("fallback");
    expect(stub).not.toBeNull();
    expect(stub!.label).not.toBe(fallback!.label);
  });

  // 필드가 없는 응답을 "모델이 돌았다"로 해석하면 이 태스크의 목적이 무너진다.
  it("필드가 없으면 모델이 돌았다고 가정하지 않는다", () => {
    expect(llmStatusNotice(undefined)).not.toBeNull();
  });
});
```

- [ ] **Step 8: 테스트가 실패하는지 확인**

Run: `cd apps/web && yarn vitest run src/components/__tests__/Diagnosis.test.tsx`
Expected: FAIL — `llmStatusNotice` 를 export 하지 않는다.

- [ ] **Step 9: llmStatusNotice 구현**

`apps/web/src/components/Diagnosis.tsx` 에서 `overallStatusTone` 바로 아래에 추가하고
export 한다:

```tsx
// llmStatus 는 이번 요청이 실제로 어느 경로로 갔는지다(설정이 아니다).
// "real" 이 아닌 모든 경우 — 값이 없는 경우 포함 — 를 드러낸다. 필드가 빠진 응답을
// 조용히 "모델이 돌았다"로 읽으면 이 표시가 존재할 이유가 사라진다.
export function llmStatusNotice(
  llmStatus: string | undefined
): { label: string; tone: "warning" | "neutral" } | null {
  if (llmStatus === "real") return null;
  if (llmStatus === "stub") {
    return { label: "스텁 응답 (모델 미사용)", tone: "neutral" };
  }
  return { label: "규칙 기반 결과 — 모델 미사용", tone: "warning" };
}
```

- [ ] **Step 10: 모달에 표시**

`Diagnosis.tsx` 의 검증 모달에서 `modalCardHead` 블록을 다음으로 교체한다:

```tsx
            <div className={styles.modalCardHead}>
              <Badge tone={overallStatusTone(validationModal.result?.overallStatus)}>
                {validationModal.result?.overallStatus ?? validationModal.status}
              </Badge>
              {(() => {
                const notice = llmStatusNotice(validationModal.result?.llmStatus);
                return notice ? <Badge tone={notice.tone}>{notice.label}</Badge> : null;
              })()}
            </div>
```

- [ ] **Step 11: 테스트 통과 확인**

Run: `cd apps/web && yarn vitest run src/components/__tests__/Diagnosis.test.tsx`
Expected: PASS

- [ ] **Step 12: 전체 웹 테스트 확인**

Run: `cd apps/web && yarn vitest run`
Expected: 기존 통과 수 + 4

- [ ] **Step 13: 커밋**

```bash
git add apps/web/src/services/history.ts apps/web/src/components/Diagnosis.tsx apps/web/src/components/__tests__/Diagnosis.test.tsx
git commit -m "feat(web): 검증 결과에 모델 미사용 여부 표시"
```

---

## 완료 확인

spec §11 의 여덟 항목을 확인한다.

```bash
grep -rn "ChatGoogleGenerativeAI\|GEMINI_API_KEY" services/prescription/prescription_api.py services/prescription/certificate_api.py services/validation-agent/app/
```

기대: 출력 없음.

```bash
grep -n "OPENAI_API_KEY\|GEMINI_API_KEY\|LLM_API_KEY" infra/docker-compose.yml
```

기대: `LLM_API_KEY` 가 `llm-gateway` 블록에만 나타난다.

```bash
cd services/llm-gateway && python -m pytest -v
cd ../validation-agent && python -m pytest -v
cd ../prescription && python -m pytest -v
```

기대: 전부 통과.

```bash
export BOOTSTRAP_SUPERUSER_PASSWORD=$(grep -m1 '^BOOTSTRAP_SUPERUSER_PASSWORD=' infra/.env | cut -d= -f2- | tr -d '\r')
python -m pytest tests/e2e -q
```

기대: 23 통과 (GC-4 — stub 경로는 손대지 않았다).

수동 확인:
- `docker compose up -d` 후 게이트웨이 헬스체크 통과
- `LLM_GATEWAY_BASE_URL` 을 비운 채 검증 에이전트를 호출하면 응답의 `llmStatus` 가 `fallback` 이고 `reasoningTrace` 항목의 `source` 가 `fallback` 이다
