# B0 — LLM 접근 계층 통일과 Bedrock 이관 설계

**작성일:** 2026-08-28
**대상:** `services/*` 의 LLM 호출 경로 전체
**선행 결정:** `Docs/superpowers/specs/2026-08-28-llm-provider-tradeoffs.md` (Bedrock `bedrock-mantle`, us-west-2, `openai.gpt-5.6-luna` 단일화)
**후속:** B1(API 활용 서비스 비판적 검토) → B2(Grounding/Verification 레이어)

---

## 1. 배경

### 1.1 왜 지금인가

Phase A 완료 후 다음은 B(Grounding/Verification)였다. 그런데 **검증 레이어를 붙일 표면이 통일돼 있지 않다.** provider 2개, 모델 ID 3개, raw HTTP 와 LangChain 래퍼가 혼재한다. 이 상태에서 검증 계층을 얹으면 서비스마다 다른 방식으로 우회된다. B0 는 그 표면을 먼저 하나로 만든다.

### 1.2 현재 상태

| 서비스 | 클라이언트 | 모델 | 타임아웃 | 재시도 |
|---|---|---|---|---|
| `prescription` | `ChatGoogleGenerativeAI` + raw httpx 분기 | `gemini-2.5-flash` | OpenAI 경로만 180s | 없음 |
| `certificate` | `ChatGoogleGenerativeAI` | `gemini-2.0-flash` | 없음 | 없음 |
| `validation-agent` | `ChatOpenAI` | OpenAI, ReAct 4회 | 없음 | 없음 |
| `evals` (양쪽) | raw httpx | 양쪽 혼재 | 부분 | 없음 |

공용 LLM 모듈이 없다. `packages/graph-etl` 은 서비스가 설치해 쓰는 라이브러리가 아니라 독립 ETL 스크립트 모음이므로 공유 패키지 선례가 아니다. 각 서비스의 Docker 빌드 컨텍스트가 자기 디렉터리로 한정돼 있어(`context: ../services/prescription` 등) 현재 구조로는 `packages/` 아래 공유 코드에 손이 닿지 않는다.

### 1.3 발견한 결함 — 이것이 B0 의 실질 목표다

**검증 에이전트가 LLM 없이도 조용히 동작한다.**

`services/validation-agent/app/agent.py` 의 `_create_llm()` 은 `OPENAI_API_KEY` 가 없으면 `None` 을 돌려주고, `_decide_next_tool()` 은 그때 `_fallback_tool_decision()` 이라는 하드코딩 휴리스틱으로 넘어간다. **응답 어디에도 그 사실이 드러나지 않는다.**

더 나쁜 것은 폴백이 만들어내는 `thought` 필드다:

```
"thought": "먼저 X-ray 추론 결과를 검증 컨텍스트로 로드한다."
"thought": "저장 상병, 증상, X-ray 추론 결과의 일관성을 먼저 확인한다."
```

LLM 이 추론한 것처럼 읽히지만 고정 문자열이다. **추론 트레이스가 추론하지 않은 결과를 추론한 것처럼 보여준다.**

Phase A 가 `engineStatus` 를 만든 이유와 같은 문제다 — "mock 을 real 로 제시하지 않는다". 그때는 X-ray 엔진에 적용했고 여기는 빠져 있다. B2 의 목표가 할루시네이션 억제인 이상, "LLM 이 안 돌았는데 돈 것처럼 보이는" 상태를 남겨두면 목표와 모순된다.

부수적으로 `prescription_api` 에는 Gemini 키가 유출 신고로 차단되는 경우를 위한 503 특례가 있다. Bedrock IAM 이관으로 이 문제의 원인 자체가 사라진다.

---

## 2. 결정 사항

브레인스토밍에서 확정한 네 가지다.

| # | 질문 | 결정 |
|---|---|---|
| 1 | LLM 사용 불가 시 동작 | **폴백은 유지하되 응답에 명시한다** (§6) |
| 2 | 공통 클라이언트 위치 | **게이트웨이 서비스** (§3) |
| 3 | stub 위치 | **서비스에 유지, 게이트웨이 우회** (§3.3) |
| 4 | 이관 범위 | **게이트웨이 + 프로덕션 3개. `evals` 는 이후** (§9) |

---

## 3. 아키텍처

### 3.1 구조

새 서비스 `services/llm-gateway/` (FastAPI). 상류는 `https://bedrock-mantle.us-west-2.api.aws/openai/v1`.

```
prescription ─┐
certificate  ─┼─→ llm-gateway ─→ Bedrock mantle (us-west-2)
validation   ─┘        ▲
                       └─ AWS 자격증명은 여기에만 존재
```

각 서비스는 `ChatOpenAI(base_url=<게이트웨이>)` 로 붙는다. mantle 이 OpenAI SDK 호환이고 게이트웨이도 같은 표면을 노출하므로, 서비스 쪽 변경은 클라이언트 생성부 한 곳이다.

### 3.2 경계 규칙

**게이트웨이는 도메인 모양을 모른다.** 처방 JSON 이나 툴 결정 스키마를 파싱하기 시작하면 그것은 게이트웨이가 아니라 두 번째 애플리케이션 계층이다. 이 규칙이 무너지면 B0 가 해결하려던 분산 문제가 게이트웨이 안으로 옮겨올 뿐이다.

**하는 일:** 상류 호출, 타임아웃 통일, 재시도, 파라미터 정규화(§5), 계측(§7), 실패의 일관된 분류.

**하지 않는 일:** 도메인 스키마 인지, 프롬프트 생성·수정, 응답 캐싱(초기 범위 밖), 모델 라우팅(단일 모델이므로 불필요).

### 3.3 stub 경로

`LLM_PROVIDER=stub` 이면 서비스는 **게이트웨이를 호출하지 않는다.** 기존 서비스 내부 stub 으로 간다.

이유: 현재 stub 은 도메인에 특화돼 있다. `stub_prescription_response(top_rx)` 는 처방 JSON 모양이고 `stub_tool_decision(iteration)` 은 툴 선택 순서다. 범용 게이트웨이가 이것들을 만들어내려면 도메인 스키마를 알아야 하고, 그러면 §3.2 가 무너진다.

부수 효과로 기존 stub 기반 CI·E2E 가 손대지 않고 그대로 유효하다. 대신 **게이트웨이 자체는 stub 경로로 검증되지 않으므로 전용 테스트가 필요하다**(§8).

---

## 4. 게이트웨이 인터페이스

OpenAI 호환 표면을 노출한다.

| 경로 | 용도 |
|---|---|
| `POST /v1/chat/completions` | 프로덕션 3개 서비스가 쓰는 경로 |
| `GET /health` | compose·ALB 헬스체크 |
| `GET /metrics` (선택) | 계측 노출. 초기에는 구조화 로그로 충분하므로 필수 아님 |

`/v1/responses` 는 초기 범위에 넣지 않는다. 현재 서비스 중 Responses API 를 쓰는 곳이 없고, 필요해지면 그때 추가한다.

---

## 5. 파라미터 계약 — 게이트웨이가 소유한다

### 5.1 근거

`gpt-5.6-luna` 는 이전 세대와 파라미터가 다르다. 확인한 사실:

**공식 문서(developers.openai.com)에서 확인:**
- `reasoning_effort` 지원 — `none`, `low`, `medium`(기본), `high`, `xhigh`, `max`
- 최대 입력 922,000 / 최대 출력 128,000, **"max output tokens"** 용어 사용
- Chat Completions 와 Responses 양쪽 지원
- `temperature`, `top_p`, `response_format` 에 대한 지원 여부는 **명시하지 않음**

**같은 사용자의 `BG_app` 프로젝트(luna 사용, C#)에서 확인:**
- `reasoning_effort` 를 보낸다 (기본값 `low`)
- **`temperature` 를 보내지 않는다**
- `max_tokens` 가 아니라 `max_completion_tokens` (해당 줄은 주석 처리 상태)

**아직 확인하지 않은 것:** luna 가 `temperature` 를 **거부**하는지 여부. 확인된 것은 "BG_app 이 보내지 않는다"와 "문서가 명시하지 않는다" 두 가지뿐이다. 추론형 모델이 거부하는 것이 흔한 패턴이므로 가능성이 높다고 볼 뿐이며, §10 의 실측 항목으로 둔다.

현재 코드는 양쪽 모두 `temperature` 를 넘긴다 — `prescription_api` 는 `DEFAULT_TEMPERATURE`, `validation-agent` 는 `ChatOpenAI(temperature=0)`. 그대로 두면 깨질 가능성이 높다.

### 5.2 정규화 규칙

| 들어오는 것 | 게이트웨이 처리 |
|---|---|
| `temperature` | 제거하고 경고 로그 |
| `top_p` | 제거하고 경고 로그 |
| `max_tokens` | `max_completion_tokens` 로 변환 |
| `reasoning_effort` 누락 | 설정된 기본값 주입 |
| `response_format` | 그대로 전달 (§10 실측 대상) |
| 그 외 | 그대로 전달 |

**조용히 버리지 않는다.** 드롭·변환할 때마다 로그를 남긴다. 그렇지 않으면 서비스가 `temperature=0.8` 을 보내고 무시당한 것을 모른 채 출력 비결정성을 디버깅하게 된다.

이 책임을 게이트웨이에 두는 것이 §3.2 와 충돌하지 않는 이유: **파라미터 계약은 전송 계층 관심사이지 도메인 스키마가 아니다.** 게이트웨이는 "이 모델이 어떤 필드를 받는가"만 알며, 그 필드에 담긴 값의 의미는 모른다.

### 5.3 기본값

| 설정 | 기본값 | 환경변수 |
|---|---|---|
| `reasoning_effort` | `low` | `LLM_REASONING_EFFORT` |
| 요청 타임아웃 | 120초 | `LLM_TIMEOUT_SECONDS` |
| 최대 재시도 | 2회 | `LLM_MAX_RETRIES` |

`reasoning_effort` 기본을 `low` 로 두는 이유: `BG_app` 이 그 값을 쓰고 있고, 이 프로젝트의 호출은 대부분 구조화 출력과 툴 선택이라 긴 추론이 필요하지 않다. 품질이 부족하면 설정으로 올린다.

---

## 6. 실패와 폴백

### 6.1 2계층 책임

- **게이트웨이**: 일시적 실패(429, 5xx, 연결 오류)를 지수 백오프로 재시도한다. 상한을 넘기면 **타입이 있는 에러**를 돌려준다. 도메인 판단을 하지 않는다.
- **서비스**: 그 에러를 받아 "저하시킬지 실패시킬지"를 결정한다. **저하시켰다면 반드시 응답에 드러낸다.**

재시도 대상: `429`, `5xx`, 연결·타임아웃 오류. 재시도 대상 아님: `4xx`(429 제외) — 요청이 잘못된 것이므로 재시도해도 같다.

### 6.2 `llmStatus` — Phase A `engineStatus` 선례를 따른다

LLM 을 쓰는 응답에 `llmStatus` 필드를 추가한다.

| 값 | 의미 |
|---|---|
| `real` | LLM 응답을 실제로 사용했다 |
| `stub` | stub provider 로 처리했다 |
| `fallback` | LLM 을 쓸 수 없어 휴리스틱으로 처리했다 |

`engineStatus` 와 마찬가지로 **환경변수가 아니라 실제 실행 경로에서 도출한다.** "설정상 real 이므로 real" 이 아니라 "LLM 응답을 실제로 받았으므로 real" 이어야 한다.

### 6.3 폴백 트레이스 표시

`validation-agent` 의 폴백 `thought` 가 LLM 추론처럼 읽히는 문제(§1.3)를 고친다. 폴백 경로에서 생성된 항목은 트레이스 자체에서 구분되어야 한다 — 최소한 해당 스텝이 휴리스틱 산물임을 나타내는 표시가 있어야 하며, 사람이 트레이스만 보고 LLM 추론으로 오인할 수 없어야 한다.

구체적 표현 방식(필드 추가 vs 접두어)은 구현 단계에서 정하되, **판정 기준은 "트레이스만 보고 구분 가능한가"** 다.

---

## 7. 계측

요청마다 구조화 로그로 남긴다.

| 항목 | 비고 |
|---|---|
| 모델 ID | |
| 입력·출력 토큰 | 상류 응답의 usage |
| 지연 | 재시도 포함 총시간과 최종 시도 시간 |
| 재시도 횟수 | |
| 결과 | `success` / `success_after_retry` / `failed` |
| 드롭·변환된 파라미터 | §5.2 |
| 호출 서비스 | 헤더로 식별 |

비용은 토큰 × 단가로 계산한다. 단가는 설정값으로 둔다(문서 기준 272K 컨텍스트 Global CRIS: 입력 $0.20 / 출력 $1.20 per 1M — 변동하므로 하드코딩하지 않는다).

로그는 CloudWatch Logs 로 보낸다. 대시보드·알람 구성은 B0 범위 밖이며 로그 스키마만 갖춘다.

---

## 8. 테스트

| 대상 | 내용 |
|---|---|
| 게이트웨이 단위 | 가짜 상류로 재시도(429·5xx), 타임아웃, 에러 분류, 계측 필드 |
| 파라미터 계약 | `temperature`·`top_p` 제거, `max_tokens` → `max_completion_tokens`, `reasoning_effort` 주입, 드롭 시 로그 |
| `llmStatus` 회귀 | 폴백 시 `fallback` 이 나오는가, `real` 이 실제 LLM 응답에서만 나오는가 |
| 폴백 트레이스 | 폴백 스텝이 LLM 추론과 구분되는가 |
| 서비스 stub 경로 | 손대지 않으므로 기존 테스트가 그대로 통과해야 한다 |
| 실측 (수동 1회) | §10 |

---

## 9. 범위

**포함:** `services/llm-gateway/` 신설, `validation-agent`·`prescription`·`certificate` 이관, Gemini 제거(프로덕션 경로), `llmStatus` 도입, 폴백 트레이스 표시, compose 스택 편입.

**제외:**

| 항목 | 이유 |
|---|---|
| `evals` 이관 | 평가 스크립트로 프로덕션 동작에 영향이 없다. provider 단일화 목적은 프로덕션 경로에서 달성된다 |
| 응답 캐싱 | mantle 이 prompt caching 을 지원하나 초기 범위 밖. 볼륨이 커지면 검토 |
| CloudWatch 대시보드·알람 | 로그 스키마만 갖추고 구성은 이후 |
| `/v1/responses` | 현재 쓰는 서비스가 없다 |
| 서비스 시나리오 문서 재정의 | 별도 작업(글로벌 EMR 전환에 따른 문서 갱신) |
| B1·B2 | 별도 spec |

---

## 10. 실측이 필요한 항목

가정으로 두면 구현 중에 터진다. 실제 Bedrock mantle 을 한 번 호출해 확인하고 **결과를 이 문서에 덧붙인다.**

- [x] **계정이 이 모델을 실제로 호출할 수 있는가 — 2026-08-28 실호출 결과 아니오.**
  이 항목은 원래 목록에 없었다. 가장 먼저 깨진 것이 목록에 없던 가정이었다.

  게이트웨이를 통해 `openai.gpt-5.6-luna` 를 치면 상류가 401 을 준다:

  ```json
  {"error":{"code":"access_denied","type":"permission_denied_error",
   "message":"openai.gpt-5.6-luna is not available for this account. ...",
   "param":null}}
  ```

  키·엔드포인트·라우트는 정상이다. 다른 모델 ID 를 치면 `validation_error`
  (`isn't supported on this route`) 나 `not_found_error` 가 나오는데, luna 만
  `access_denied` 다 — 즉 이 라우트에 모델은 존재하고 계정에 엔타이틀먼트가 없다.

  해소 방법: Bedrock 콘솔 us-west-2 의 Model access 에서 활성화. 자가 승인이
  안 되면 메시지가 AWS Sales 를 가리킨다. 그때는 계정이 가진 모델로 바꾼다
  (`aws bedrock list-foundation-models --region us-west-2`).

  **이 항목이 미해소인 동안 아래 나머지 항목은 측정 자체가 불가능하다.**
- [ ] luna 가 `temperature` 를 거부하는가, 아니면 무시하는가
- [ ] `response_format: {"type": "json_object"}` 이 mantle 에서 동작하는가 (`prescription_api` 가 의존한다)
- [ ] mantle 의 tool calling 이 LangChain `ChatOpenAI` 경유로 동작하는가 (`validation-agent` 의 ReAct 가 의존한다)
- [x] **Bedrock TPM 기본 쿼터의 10배 출력 번다운 — 문서로 확인됨(2026-08-28).** luna 모델 카드: "On the `bedrock-runtime` endpoint, limits are managed as tokens per minute (TPM) with a 10x burndown rate, where 1 output token consumes 10 tokens." mantle 쪽 쿼터는 별도 문서(quotas-mantle)이므로 실호출로 재확인한다.
- [ ] 단가가 컨텍스트 길이에 따라 두 단계다(Short 272K / Long 1M). 계측은 단일 단가만 쓴다 — 272K 를 넘는 프롬프트가 생기면 비용이 절반으로 과소 계상된다. 실제 워크로드가 그 경계에 얼마나 가까운지 측정하고, 필요하면 metering 을 두 단계로 나눈다.
- [ ] Bedrock TPM 기본 쿼터가 이 워크로드에 충분한가 (mantle 쿼터는 대기열 기반이라 runtime 과 다르다)
- [ ] 게이트웨이의 시도당 타임아웃 45초가 luna 의 실제 p95 대비 충분한가 — 낮게 잡았다면 정상 지연이 하드 실패로 바뀐다. 시도 1이 생성 도중 끊기고 부분 출력이 과금된 채 버려지며, 3회 반복 후 호출자는 136.5초 뒤 502 를 받는다. 이 값은 전체 타임아웃 사다리의 기준점이다(services/llm-gateway/app/config.py).

---

## 11. 완료 조건

1. 프로덕션 경로에 Gemini 호출이 남아 있지 않다.
2. `prescription`·`certificate`·`validation-agent` 가 모두 게이트웨이를 통해 LLM 을 호출한다.
3. AWS 자격증명을 가진 서비스가 게이트웨이 하나뿐이다.
4. `LLM_PROVIDER=stub` 에서 게이트웨이 없이 기존 테스트·E2E 가 그대로 통과한다.
5. 게이트웨이가 `temperature` 를 제거하고 `max_tokens` 를 변환하며, 그 사실을 로그로 남긴다 — 테스트로 고정한다.
6. LLM 을 쓸 수 없을 때 응답의 `llmStatus` 가 `fallback` 이고, 폴백 트레이스가 LLM 추론과 구분된다 — 테스트로 고정한다.
7. §10 의 다섯 항목이 실측되고 결과가 이 문서에 기록됐다.
8. 게이트웨이가 compose 스택에서 기동하고 헬스체크를 통과한다.
