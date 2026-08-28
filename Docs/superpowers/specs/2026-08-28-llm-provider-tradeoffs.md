# LLM 제공 경로 선택 — 트레이드오프 정리

**작성일:** 2026-08-28
**상태:** **결정됨** — Bedrock `bedrock-mantle`, us-west-2, `openai.gpt-5.6-luna` 단일화
**맥락:** 부트캠프 인프라 구축 프로젝트로 완성도를 올리는 중. 평가 대상은 **"클라우드 아키텍처 설계·운영 전반"**이며 "LLM 직접 서빙 인프라"가 아니다.

---

## 0. 결정 기록 (2026-08-28)

**채택:** 아래 §7의 선택지 **B2** — Bedrock `bedrock-mantle` 엔드포인트, us-west-2, 모델 `openai.gpt-5.6-luna` 단일화. Gemini 제거.

**포기한 것:** 서울 리전. `bedrock-mantle`은 us-east-1 / us-east-2 / us-west-2 에만 있다.

**그 포기를 어떻게 다루기로 했는가:** 리전 제약을 숨기지 않고 **서비스 시나리오 자체를 국내 EMR에서 글로벌 EMR로 재정의**한다. 프론트 서비스명을 `BitComputer EMR` → `Global EMR` 로 변경했다(로고와 브라우저 탭 제목).

이 방향을 택한 이유는 두 가지다.
1. 제약을 감추고 "왜 미국 리전인가"에 답하지 못하는 것보다, 제약을 설계 전제로 드러내는 편이 방어 가능하다.
2. structured outputs 와 server-side tool calling 을 지키는 것이 할루시네이션 억제(Phase B 목표)에 직결되므로, 둘 중 하나를 포기해야 한다면 리전 쪽이 맞다.

**따라오는 후속 작업:** 서비스 시나리오 문서(사용자 흐름·아키텍처 설명)가 국내 단일 병원 전제로 쓰여 있다면 함께 재정의해야 한다. 아직 미착수.

---

## 1. 결정할 것

1. 어떤 모델을 쓸 것인가 — `gpt-5.6-luna` 단일화 여부, Gemini 제거 여부
2. 어떤 경로로 부를 것인가 — OpenAI 직접 API vs Amazon Bedrock
3. Bedrock이면 어느 엔드포인트·리전인가

---

## 2. 확인된 사실

아래는 2026-08-28에 공식 문서로 직접 확인한 것이다. **가격·리전·기능 지원은 바뀌므로 결정 시점에 재확인 필요.**

### 2.1 `gpt-5.6-luna` (출처: developers.openai.com)

| 항목 | 값 |
|---|---|
| 컨텍스트 | 1,050,000 |
| 최대 출력 | 128,000 |
| 입력 / 출력 | $0.20 / $1.20 per 1M |
| tool calling | 지원 |
| structured outputs | 지원 |
| 지식 기준일 | 2026-02-16 |
| 포지셔닝 | 비용 민감·고volume용. 이전 GPT-5 계열 nano 티어 상당 |

### 2.2 Bedrock의 Luna (출처: docs.aws.amazon.com Bedrock model card)

- 모델 ID: `openai.gpt-5.6-luna`
- **OpenAI SDK 호환** — `OPENAI_BASE_URL` + Bedrock 장기 API 키로 붙는다
- 출시 2026-07-13, 컨텍스트 1M
- 서비스 티어: Standard만 (Priority·Flex·Reserved 미지원)
- TPM 쿼터에서 **출력 토큰이 10배로 차감**된다

**엔드포인트가 둘이고 기능이 갈린다 — 이게 이번 결정의 핵심이다.**

| | `bedrock-runtime` | `bedrock-mantle` |
|---|---|---|
| Chat Completions / Responses | 지원 / 지원 | 지원 / 지원 |
| Converse | 지원 | 미지원 |
| **structured outputs** | **미지원** | (Responses API) |
| **server-side tool calling** | **미지원** | **지원** |
| prompt caching | Responses API만 | 지원 |
| Guardrails | Converse API만 | — |
| 리전 | 서울 포함 다수, 단 **Global CRIS만** | **us-east-1 / us-east-2 / us-west-2 뿐** |

### 2.3 가격 비교 (272K 컨텍스트, per 1M)

| 경로 | 입력 | 출력 | 캐시 읽기 |
|---|---|---|---|
| OpenAI 직접 | $0.20 | $1.20 | — |
| Bedrock Global CRIS | $0.20 | $1.20 | $0.02 |
| Bedrock In-Region / Geo | $0.22 | $1.32 | $0.022 |

1M 컨텍스트 사용 시 약 2배($0.40 / $1.80). 이 워크로드는 해당 없음.

---

## 3. 현재 코드의 결합도

| 서비스 | 클라이언트 | 모델 |
|---|---|---|
| prescription | `ChatGoogleGenerativeAI` (LangChain) | `gemini-2.5-flash` |
| certificate | `ChatGoogleGenerativeAI` | `gemini-2.0-flash` |
| validation-agent | `ChatOpenAI` (LangChain) | OpenAI, ReAct 4회 반복 |
| evals | raw HTTP | 양쪽 혼재 |

- `ChatOpenAI`는 `base_url`을 받으므로 **OpenAI 호환 서버면 설정 변경으로 붙는다**
- `ChatGoogleGenerativeAI` 쪽은 교체 작업 필요
- `LLM_PROVIDER=stub` 추상화가 이미 있어 손댈 지점이 좁다
- **provider 2개 / 모델 ID 3개 / raw HTTP / LangChain 래퍼가 혼재** — 정리 자체가 다음 단계의 선행 조건

---

## 4. 비용 규모 감각

가정: 월 500회 에이전트 실행 × 4반복, 회당 입력 2K·출력 500 토큰 → **월 입력 4M / 출력 1M**

| 방식 | 월 비용 |
|---|---|
| Luna (직접 또는 Bedrock Global CRIS) | **약 $2** |
| Bedrock In-Region / Geo | 약 $2.2 |
| 자체 호스팅 `g5.xlarge` 24/7 | 약 $730 |
| 자체 호스팅 `g4dn.xlarge` 24/7 | 약 $390 |

자체 호스팅은 이 볼륨에서 **약 300~400배 비싸다.** 볼륨이 훨씬 커지기 전에는 성립하지 않는다.

---

## 5. 자체 호스팅(경량 LLM)을 접은 이유

비용 외에 **품질 리스크가 더 크다.**

- 이 워크로드는 **tool calling + 구조화 출력**이다 (ReAct 4단계, JSON 강제)
- 7B급은 이 영역이 상용 모델 대비 약하다 — 툴 이름 오류, JSON 파손 빈도가 오른다
- Phase B의 목표가 **할루시네이션 억제**인데, 경량 모델 전환은 그 목표와 정면으로 부딪힌다
- CPU 전용은 속도가 안 나온다: 7B 양자화 CPU 추론 5~15 tok/s면 4반복 ReAct 한 번에 수 분

즉 **비용을 수백 배 더 쓰면서 정확도는 떨어지는** 조합이 될 수 있다.

> 참고: 과거 DACON에서 경량 모델 앙상블을 했다는 기록을 노션에서 두 가지 키워드로 검색했으나 찾지 못했다. 워크스페이스에 없거나 다른 제목으로 저장된 듯하다.

---

## 6. 핵심 트레이드오프

### 축 1 — structured outputs vs 서울 리전

이 프로젝트의 검증 에이전트는 JSON 강제 출력에 의존한다. 그런데:

- `bedrock-runtime`: 서울 쓸 수 있음(Global CRIS) / **structured outputs 없음**
- `bedrock-mantle`: structured outputs·server-side tool calling 있음 / **서울 없음** (us-east-1/2, us-west-2뿐)
- OpenAI 직접: 둘 다 해당 없음(리전 개념 없고 structured outputs 지원)

**하나를 포기해야 한다.** 할루시네이션 억제가 목표라면 structured outputs 쪽을 지키는 게 맞다고 본다.

### 축 2 — API 키 관리 vs 리전 자유도

- **OpenAI 직접**: 키를 `.env`/Secrets Manager로 관리해야 한다. 지금 이 저장소는 키가 `.env`에 있고, **유출된 Gemini/OpenAI 키 폐기가 아직 미확인**이다.
- **Bedrock**: IAM으로 붙일 수 있어 **로테이션할 키 자체가 사라진다.** 기존 결함을 구조적으로 해소한다.

### 축 3 — 데이터 레지던시

의료 EMR 서사에서 Global CRIS는 "전 세계 어디로든 라우팅"이다. 데모 데이터가 전부 합성이면 실질 문제는 없다. 다만 서사에 레지던시를 넣을 거면 걸린다 — 오히려 **"제약을 인지하고 리전을 선택했다"**가 더 성숙한 설명이 될 수 있다.

### 축 4 — 평가 대상과의 정합성

평가가 "클라우드 아키텍처 설계·운영"이므로, Bedrock을 쓰면 CloudTrail·CloudWatch·Guardrails·VPC 엔드포인트·IAM이 **네이티브로** 엮인다. OpenAI 직접이면 같은 그림을 Secrets Manager·NAT egress 제어·커스텀 지표로 직접 짜야 한다(그것도 유효한 서사지만 손이 더 간다).

---

## 7. 선택지

| | 모델 | 키 관리 | structured outputs | 리전 | AWS 통합 |
|---|---|---|---|---|---|
| **A. OpenAI 직접** | Luna | API 키(로테이션 필요) | 지원 | 무관 | 직접 구축 |
| **B1. Bedrock runtime** | Luna | IAM | **미지원** | 서울 가능(Global CRIS) | 네이티브 |
| **B2. Bedrock mantle** | Luna | IAM | 지원 | **미국 3개 리전만** | 네이티브 |
| C. 자체 호스팅 | 경량 OSS | — | 모델 의존 | 자유 | 직접 구축 |

---

## 8. 현재 권고 (확정 아님)

**B2 — Bedrock `bedrock-mantle`, us-west-2.**

근거:
1. structured outputs와 server-side tool calling이 살아 있다 (할루시네이션 억제 목표와 정합)
2. IAM 인증으로 키 유출 문제가 구조적으로 사라진다
3. 가격이 직접 호출과 사실상 동일하다
4. 평가 대상(클라우드 아키텍처)과 서사가 맞는다
5. 코드 변경이 작다 — `ChatOpenAI(base_url=...)` 수준

포기하는 것: **서울 리전.**

**Gemini 제거는 동의.** provider 단일화 자체가 다음 단계의 선행 조건이다.

---

## 9. 미결 사항

- [ ] `bedrock-mantle`의 structured outputs가 LangChain `ChatOpenAI`로 어떻게 노출되는지 실측 필요 (Responses API 경유)
- [ ] Bedrock TPM 쿼터 기본값이 이 워크로드에 충분한지 (출력 10배 차감 고려)
- [ ] 서울 리전 포기가 부트캠프 평가 기준에 걸리는 항목인지
- [ ] 유출된 Gemini/OpenAI 키 폐기 — Bedrock 이관과 무관하게 여전히 필요
- [ ] Bedrock 이관 시 로컬 개발·CI 경로 (`LLM_PROVIDER=stub` 유지로 커버되는지)

---

## 10. 다음 단계 제안

기존 Phase B(Grounding/Verification) 앞에 두 단계를 넣는다.

**B0 — LLM 접근 계층 통일 + Bedrock 이관**
provider 단일화(Gemini 제거), 공통 클라이언트로 타임아웃·재시도·폴백·토큰 계측 일원화, IAM 인증, CloudWatch 지표. `LLM_PROVIDER=stub`은 로컬·CI용으로 유지.

**B1 — API 활용 서비스 비판적 검토**
서비스별로 무엇이 근거 기반이고 무엇이 생성인지 분류, 실패 모드 목록화, 각 출력의 검증 가능성 판정.

**B2 — Grounding/Verification 레이어** (기존 Phase B spec §10)

이유: provider와 호출 계층을 통일하지 않은 상태에서 검증 레이어를 붙이면, 서비스마다 다른 방식으로 우회된다.
