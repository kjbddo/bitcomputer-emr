# Phase A — 기반 정비 설계

- 작성일: 2026-08-26
- 대상 프로젝트: BitComputer (EMR + AI 에이전트)
- 단계: A (전체 5단계 중 1단계)

## 1. 배경

BitComputer는 Next.js UI, Spring Boot 업무 API, 4개 Python AI 서비스, MySQL/ArangoDB/RabbitMQ/Redis로 구성된 EMR 시스템이다. 약 41k LOC 규모이며 구조 설계와 문서는 갖춰져 있으나, 전수 점검 결과 핵심 기능이 비어 있거나 연결되지 않은 상태다.

### 1.1 점검에서 확인된 문제

심각도순으로 정리한다. 각 항목은 실제 코드에서 확인했다.

**S0 — 보안**

| # | 문제 | 위치 |
|---|---|---|
| 1 | 인증 완전 비활성화. `anyRequest().permitAll()`, JWT 필터 주석 처리. 환자 개인정보·진료기록 전 API 무인증 노출 | `SecurityConfig.java:42` |
| 2 | 실 API 키 커밋 유출: Gemini 키, MySQL root 비밀번호, JWT secret | `application-local.properties:14,39,43` |
| 3 | 실 API 키 커밋 유출: OpenAI 키, Gemini 키 | `ValidationAgent/evals/.env` (커밋 `812c9cb`) |
| 4 | JWT secret 하드코딩 | `application.properties:33` |
| 5 | 프론트 토큰이 localStorage + non-HttpOnly 쿠키. XSS 탈취 가능 | `token.ts:29` |
| 6 | `middleware.ts`가 쿠키 존재 여부만 확인, 서명 검증 없음 → 임의 쿠키로 우회 | `middleware.ts:6` |
| 7 | CORS allowedOrigins에 리터럴 플레이스홀더 `"클라이언트 주소"` | `SecurityConfig.java:52` |

**S1 — AI 파이프라인**

| # | 문제 | 위치 |
|---|---|---|
| 8 | 배포 구성이 전부 mock (`USE_TORCH_*=false`). 실행되는 것은 `MockAnomalyModel` + `MockROIModel` + 고정 시드 random projection 임베딩. 그런데 `MODEL_VERSION=ae_squid_v1`로 실제 모델처럼 라벨링됨 | `docker-compose.yml`, `ml/factory.py` |
| 9 | `USE_TORCH_ROI`가 no-op. 실 ROI 어댑터 자체가 없음 | `ml/factory.py:22` |
| 10 | 자체 eval이 검색 무신호를 증명: `precision@1 = 0.753` vs `precision@20 = 0.735` (평평한 정밀도 곡선 = 순위가 라벨과 무관). per-disease top1이 atelectasis·cardiomegaly·pleural_effusion·edema·consolidation·pneumonia·pneumothorax 전부 0.0 | `storage/eval/with_roi/metrics.json` |
| 11 | `bilateral_diffuse_error` 태그가 174/174 케이스에 등장 = 정보량 0 | 위와 동일 |
| 12 | score가 총합 정규화 결과라 확신도가 아닌 상대 지분. 근거가 없어도 top1은 큰 값 | `domain/scoring.py:52` |
| 13 | 위 지분 값에 `>= 0.35` 임계를 걸어 "고신뢰 소견"으로 취급 — 서비스 경계를 넘는 의미론 오류 | `ValidationAgent/app/tools.py:52` |
| 14 | 처방 추천에 grounding 검증 없음. LLM이 낸 `name`/`prescription_code`를 근거·마스터와 대조하지 않음. 존재하지 않는 코드도 그대로 반환 | `prescription_api.py:635` |
| 15 | `prescriptions` 길이 3 강제 → 데이터 부족 시에도 3칸을 채워야 함 (구조적 지어내기 유도) | `prescription_agent.py:265` |
| 16 | 프롬프트가 `reason` 안에서 일반 의학·약리 지식 보강을 명시 허용. 검증 단계 없음 | `prescription_agent.py:42` |

**S2 — 에이전트 구조**

| # | 문제 | 위치 |
|---|---|---|
| 17 | LangGraph 실행 경로가 현재 도달 불가. `_build_graph()`가 호출되지 않아 `_load_context`·`_route_next_action`·`_finalize_validation`·`_llm_finalize`가 실행되지 않고, 실제 실행은 수동 for 루프다. **원인은 의도적 폐기가 아니라 API 재설계 과정에서 호출부가 유실된 것**이며, 해당 구현은 여전히 유효하다. C단계에서 제거가 아니라 **복구·활용 방향**으로 다룬다 | `agent.py:794`, `agent.py:94` |
| 18 | "필요에 따라 툴 선택"이 실제로는 미작동. ReAct 루프 바깥에서 pubmed와 prescription_finder를 무조건 호출 | `agent.py:115,125` |
| 19 | `prescription_validator`가 스텁. 처방+상병이 있으면 무조건 `APPROPRIATE`. 상호작용·금기·용량 검사 0건 | `tools.py:147` |
| 20 | 19번의 evidence 문자열이 "LLM 최종 검토 단계에서 평가"라고 적혀 있으나 그 단계는 17번의 죽은 코드. 결과적으로 처방은 어디서도 검증되지 않음 | `tools.py:149` |
| 21 | `disease_validator`가 8개 하드코딩 키워드 부분문자열 매칭. 미등록 질병은 underscore 변형이라 한글 상병명과 절대 매칭 안 됨 | `tools.py:11-21,54` |
| 22 | PubMed 초록이 주장을 지지하는지 판정하는 단계 없음 → 무관한 인용이 신뢰도 착시 유발 | `tools.py:pubmed_loader` |
| 23 | eval 신뢰 불가: `caseCount: 2`, `skipJudges: true`, `judgeProviders: []`인데 리포트는 `Hallucination rate: 0.0`, `Safety pass rate: 1.0`으로 출력 | `eval_summary_20260520T064851Z.json` |

**S3 — 공학 기반**

| # | 문제 |
|---|---|
| 24 | 루트 git 손상(`.git/HEAD`가 `ref: refs/heads/`). 하위 6개가 각각 독립 GitHub repo, submodule도 monorepo도 아님 → 전체 스냅샷 재현 불가 |
| 25 | `AI_BackEnd/.git` 636MB — CheXmask `.pt` 7개 × 70MB 커밋, LFS 없음 |
| 26 | 테스트 사실상 없음. Spring 14개(main 147개 대비), Python 4개 서비스 전부 0개. `XrayGraphRAG/pytest.ini`가 존재하지 않는 `tests` 디렉터리를 가리킴. Front-End는 테스트 러너 미설치 |
| 27 | Spring 계층 위반: Patient·Phrase·SuperUser·ValidationJob·ValidationResult 컨트롤러가 Repository 직접 주입. `@Transactional`은 147개 중 5개 파일 |
| 28 | Front-End 상태관리 부재. 695줄 `evaluation/page.tsx`, 685줄 `Diagnosis.tsx` |
| 29 | `xlsx@^0.18.5` — prototype pollution / ReDoS 알려진 취약, npm 배포본에 패치 없음 |
| 30 | ArangoDB를 그래프로 쓰지 않고 동시출현 빈도 집계로만 사용. traversal 활용 미미 |
| 31 | compose 결합 과다: `spring-boot`가 8개 서비스 `healthy`를 전부 대기 → 하나만 죽어도 전체 기동 실패 |
| 32 | 문서(`Docs/04`)가 코드보다 앞서 있음. LangGraph·LLM 최종판정·선택적 툴 호출 서술이 실제와 불일치 |

### 1.2 근본 진단

할루시네이션은 프롬프트 튜닝 문제가 아니다. **출력이 입력 근거와 일치하는지 검사하는 레이어가 파이프라인에 아예 없다**는 아키텍처 결손이다. 골격은 있으나 속이 비어 있다 — X-ray 추론은 mock, 처방 검증은 무조건 통과 스텁, 최종 판정 LLM은 죽은 코드, 인증은 꺼짐, 지표는 미측정을 통과로 표시.

## 2. 전체 로드맵과 A의 위치

| 단계 | 내용 | 의존 |
|---|---|---|
| **A** | 기반 정비 — 보안·저장소·테스트/CI | 없음 (나머지 전부의 전제) |
| B | Grounding/Verification 레이어 (처방 추천 할루시네이션) | A |
| C | ValidationAgent 재설계 | B의 인터페이스 |
| D | X-ray 파이프라인 (mock 제거 또는 정직화 + 재평가) | A |
| E | 웹서비스 완성도 (Spring 계층, 프론트 상태관리, 테스트 백필) | A |

각 단계는 독립된 spec → plan → 구현 → 검증 사이클을 돈다. 본 문서는 A만 다룬다.

### 2.1 프로젝트 목표 전제

- **목표 수준: 완성도 높은 포트폴리오/데모.** 실환자 데이터 없음, 합성/공개 데이터만 사용. 의료기기 SW 인허가·임상 검증 대상 아님.
- **투입: 1인, 수 개월.** A부터 E까지 순차 진행 가능.
- 이 전제에서 도출되는 원칙:
  - AI 출력은 항상 "보조 후보"로 명시 표기한다.
  - mock을 실제인 것처럼 표기하는 상태는 허용하지 않는다. 포트폴리오에서 가장 치명적인 결함이다.
  - 개선의 가치는 **증명 가능성**에 있다. 측정 없는 개선 주장은 하지 않는다.

## 3. A 단계 범위

### 3.1 한 문장 목표

이후 모든 개선을 증명 가능하게 만드는 토대를 세운다.

### 3.2 포함

- 새 monorepo 구성, 기존 6개 repo archive 처리
- 커밋 히스토리에서 유출 키·거대 가중치 격리
- 인증 복구: JWT 필터 재가동, HttpOnly 쿠키 전환, 역할별 엔드포인트 권한
- 환자 기록 접근 감사 로그
- 시크릿 관리 체계 (`.env.example` 규약 + fail-fast 검증 + gitleaks)
- CI 파이프라인, 서비스별 테스트 러너, smoke test, E2E 1개
- compose 의존성 완화

### 3.3 제외 (후속 단계)

A는 **이동과 배선**이지 재작성이 아니다. 이 구분을 지키지 않으면 스코프가 폭발한다.

- AI 로직 변경 없음 — 처방 추천, X-ray, ValidationAgent 코드는 그대로 옮긴다 (아래 3.4의 두 예외 제외)
- Spring 계층 위반 수정 → E
- 프론트 상태관리 재설계 → E
- `xlsx` 취약 의존성 교체 → E
- mock 제거·재평가 → D
- grounding 검증 레이어 → B
- ValidationAgent 그래프 실행 경로 복구 → C

### 3.4 "AI 로직 변경 없음" 원칙의 명시적 예외 2건

**예외 1 — `engineStatus` 정직성 필드**

X-ray 추론 응답과 처방 추천 응답에 현재 엔진 상태를 나타내는 필드를 추가한다.

```json
{ "engineStatus": "mock" }
```

허용값은 `mock` | `real` | `stub`이며, 값은 실행 시점 설정에서 파생한다. 서비스별로 나올 수 있는 값이 다르다.

| 서비스 | 파생 기준 | 가능한 값 |
|---|---|---|
| `xray-rag` | `USE_TORCH_ANOMALY` && `USE_TORCH_EMBEDDING` | 둘 다 true면 `real`, 아니면 `mock` |
| `prescription` | `LLM_PROVIDER` | `stub` 또는 `real` |
| `validation-agent` | `LLM_PROVIDER` | `stub` 또는 `real` |

`xray-rag`는 `stub`을 쓰지 않고(LLM 미사용), `prescription`·`validation-agent`는 `mock`을 쓰지 않는다.

프론트는 이 값이 `real`이 아니면 결과 화면에 경고 배지를 표시한다.

근거: D단계까지 수 개월간 "실제인 척하는 시스템"으로 남는 것을 막는다. 작업량은 작고 정직성 이득은 크다.

**예외 2 — `LLM_PROVIDER=stub` 모드**

결정론적 고정 응답을 돌려주는 LLM provider를 주입 지점에 추가한다. 기존 LLM 호출 로직은 건드리지 않고 분기만 추가한다.

근거:
- CI에서 실제 LLM을 호출할 수 없다(키·비용). stub이 없으면 E2E가 AI 경로를 검증하지 못해 반쪽이 된다.
- B단계에서 필수 재료다. grounding 검증 레이어의 효과를 측정하려면 LLM 출력을 고정할 수 있어야 한다.

대상: `services/prescription` (Gemini/OpenAI), `services/validation-agent` (OpenAI).

## 4. 저장소 구조

### 4.1 통합 방식

**새 monorepo로 출발한다.** 현재 코드 스냅샷으로 단일 저장소를 시작하고, 기존 6개 repo는 GitHub에서 archive 처리해 이력을 보존한다.

`git subtree` 히스토리 병합을 택하지 않은 이유:
- 유출 키가 히스토리에 남아 있어 `git-filter-repo` 선행 작업이 필요하고, 실수 시 유출이 잔존한다
- 636MB 가중치도 별도 제거가 필요하다
- 커밋 메시지 상당수가 `.` 한 글자라 보존 가치가 낮다

### 4.2 레이아웃

```
bitcomputer/
├── apps/
│   ├── web/                    # Next.js          (구 Front-End)
│   └── api/                    # Spring Boot      (구 Back-End)
├── services/
│   ├── xray-rag/               # FastAPI          (구 XrayGraphRAG)
│   ├── prescription/           # FastAPI          (구 GraphDB/langchain_graph_qa)
│   ├── validation-agent/       # FastAPI          (구 ValidationAgent)
│   └── radiology-legacy/       # Flask            (구 AI_BackEnd)
├── packages/
│   └── graph-etl/              # CSV 정규화       (구 GraphDB/data_normalize)
├── infra/
│   ├── docker-compose.yml
│   └── .env.example
├── docs/
│   ├── superpowers/specs/
│   └── (기존 Docs/ 내용 이관)
├── scripts/
│   └── fetch-models.sh
└── .github/workflows/
```

`Back-End`/`Front-End`는 계층 이름이지 앱 이름이 아니므로 `apps/api`/`apps/web`으로 변경한다. 경로 참조(문서, compose, 스크립트, IDE 설정)를 함께 갱신한다.

`services/prescription`은 현재 처방 추천 API와 진단서 생성 API가 같은 디렉터리에서 두 개 uvicorn 프로세스로 뜬다. A에서는 디렉터리 이동만 하고 서비스 분리는 하지 않는다.

### 4.3 모델 가중치 처리

저장소에 커밋하지 않는다.

| 대상 | 크기 | 처리 |
|---|---|---|
| CheXmask `*.pt` × 7 | 490MB | 공개 데이터셋 → 원본 URL 다운로드 |
| SQUID `model.pth` | 204MB | 본인 학습 산출물 → GitHub Release asset |
| SQUID `discriminator.pth` | 2.8MB | 동일 |

`models/` 디렉터리는 `.gitignore` 대상이다. `scripts/fetch-models.sh`가 SHA256 매니페스트를 기준으로 내려받고 체크섬을 검증한다. 체크섬 불일치 시 실패한다.

결과: 클론이 수 초로 끝나고, CI는 가중치 없이 mock 경로로 통과할 수 있다.

## 5. 인증 · RBAC · 감사 로그

### 5.1 재사용 가능한 기존 자산

이미 구현되어 있으나 연결되지 않은 것들이다. 새로 만들지 않는다.

- `Role` enum (`DEFAULT`, `SUPER_USER`, `DOCTOR`, `NURSE`, `RECEPTIONIST`)
- `JwtTokenProvider`, `JwtAuthenticationFilter`, `TokenInfo`
- `TokenBlacklistService` (Redis 기반)
- `Employee` 엔티티 (username, password, role, deptId)

### 5.2 JWT 복구

`SecurityConfig`의 주석 해제만으로는 부족하다. 아래를 함께 처리한다.

1. `jwt.secret` 하드코딩 제거 → `${JWT_SECRET}`. 부팅 시 길이 검증(HS256 최소 256bit). 현재 `Keys.hmacShaKeyFor(secretKey.getBytes())`는 짧으면 런타임에 실패하므로, 시작 시점에 잡는다.
2. access token을 **HttpOnly + Secure + SameSite=Lax 쿠키**로 전달. 프론트 `localStorage` 저장 제거.
3. 로그아웃 시 Redis 블랙리스트 등록, 필터에서 확인.
4. CORS `allowedOrigins`의 리터럴 `"클라이언트 주소"` 제거, 환경변수화.
5. CSRF: 쿠키 기반 인증으로 전환하므로 현재의 전면 `csrf.disable()`을 해제한다. Spring의 `CookieCsrfTokenRepository.withHttpOnlyFalse()`를 사용해 SPA가 읽을 수 있는 `XSRF-TOKEN` 쿠키를 발급하고, 프론트 axios 인스턴스에 `xsrfCookieName`/`xsrfHeaderName`을 설정한다. `GET`·`HEAD`·`OPTIONS`는 Spring 기본대로 검사에서 제외된다.

토큰 만료는 8시간으로 한다(교대 근무 1회 커버). refresh token 회전은 본 스코프 밖이며, 만료 시 재로그인한다.

`middleware.ts`는 쿠키 존재 여부만 보는 **낙관적 리다이렉트**로 남긴다. 이는 UX 장치이지 방어 계층이 아니다. 이 사실을 코드 주석과 문서에 명시한다. 실제 권한 판정은 서버에서만 수행한다.

### 5.3 RBAC 매핑

| 역할 | 권한 |
|---|---|
| `DEFAULT` | 없음. 가입 직후 승인 대기 상태 |
| `RECEPTIONIST` | 환자 등록·조회, 대기 등록 |
| `NURSE` | 환자 조회, 대기 관리, 진료 이력 읽기, **처방 조회(읽기)** |
| `DOCTOR` | 진료 기록 작성, 상병·처방 등록, AI 기능 전체, 진단서 발급 |
| `SUPER_USER` | 역할 부여, 마스터 코드 관리, 감사 로그 열람 |

**설계 결정 — AI 엔드포인트는 `DOCTOR` 전용이다.**

대상: `AgentController`, `AgentDocumentController`, `ValidationJobController`, `RadiologyReportController`.

근거: 처방 추천과 진단서 생성은 임상 판단이 개입하는 지점이므로 접근 자체를 의사로 제한한다.

**구분 — "처방 조회"와 "AI 처방 추천 호출"은 별개다.** `NURSE`는 등록된 처방을 조회할 수 있으나(투약 업무상 필요), 새 추천을 생성하는 `AgentController`에는 접근할 수 없다.

### 5.4 감사 로그

환자 식별자를 다루는 엔드포인트에 `@AuditPatientAccess` 애너테이션을 붙이고, 인터셉터가 기록한다.

```
access_audit_log
  id                  BIGINT PK
  occurred_at         DATETIME
  actor_employee_id   INT
  actor_username      VARCHAR
  actor_role          VARCHAR
  action              VARCHAR      -- 예: PATIENT_VIEW, PRESCRIPTION_CREATE
  target_patient_id   INT NULL
  target_history_id   INT NULL
  request_ip          VARCHAR
  outcome             VARCHAR      -- GRANTED | DENIED
  detail              TEXT NULL
```

**AOP 전면 적용 대신 애너테이션 방식을 택한 근거:** 어떤 엔드포인트가 환자 데이터를 만지는지가 코드에 명시적으로 드러난다. 감사 대상 목록이 곧 문서 역할을 한다.

정책:
- 테이블은 append-only. 애플리케이션에 수정·삭제 API를 만들지 않는다.
- 조회는 `SUPER_USER`만 가능하다.
- 권한 거부(`DENIED`)도 기록한다. 접근 **시도** 자체가 감사 대상이다.

## 6. 시크릿 관리

### 6.1 현황

시크릿이 `.env.docker`, `GraphDB/langchain_graph_qa/.env`, `XrayGraphRAG/.env`, `ValidationAgent/evals/.env`, `application-local.properties`에 흩어져 있고 일부는 커밋되어 있다.

### 6.2 통합 규약

`infra/.env.example` 하나로 통합한다. 규약:

- `.env`는 `.gitignore` 대상, `.env.example`은 항상 같은 커밋에서 동기화한다
- `.env`의 모든 키를 같은 순서로 나열한다. 키가 빠지면 다른 환경에서 조용히 기본값으로 떨어진다
- 노출 금지 값(`OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `MYSQL_ROOT_PASSWORD`, `ARANGO_PASSWORD`, `JWT_SECRET`)은 `키=` 형태로 비워 둔다
- 노출되어도 무방한 값(`GEMINI_MODEL`, `OPENAI_MODEL`, `XRAY_API_DEFAULT_VIEW`, 포트)은 실제 기본값을 적는다
- 선택지가 정해진 항목은 바로 위에 유효값 주석을 남긴다 (예: `# xray | flask`, `# gemini | openai | stub`)

### 6.3 Fail-fast 검증

현재는 필수 환경변수가 비어도 서비스가 조용히 뜨고 런타임에 불명확하게 실패한다. 각 서비스 부팅 시 필수 환경변수 존재를 확인하고, 없으면 명확한 메시지와 함께 즉시 종료한다.

### 6.4 CI 시크릿 — GitHub Secrets

GitHub Secrets는 `.env.example` 규약을 대체하지 않고 **보완**한다. Actions 러너 안에서만 주입되므로 로컬 개발이나 `docker compose up`에는 사용할 수 없다.

| 환경 | 시크릿 출처 |
|---|---|
| 로컬 개발 / docker compose | `infra/.env` (gitignore, `.env.example`로 형태만 공유) |
| GitHub Actions CI | GitHub Secrets (repository secrets) |

**CI에 필요한 시크릿은 최소화한다.** E2E는 `LLM_PROVIDER=stub`으로 돌므로 LLM 키가 불필요하고, DB·메시지큐 비밀번호는 CI 컨테이너 전용 임시값이면 충분하다.

| 이름 | CI 필요 여부 | 비고 |
|---|---|---|
| `JWT_SECRET` | 필요 | CI 전용 값. 운영 값과 달라야 한다 |
| `MYSQL_ROOT_PASSWORD` | 필요 | CI 컨테이너 전용 임시값 |
| `ARANGO_PASSWORD` | 필요 | CI 컨테이너 전용 임시값 |
| `OPENAI_API_KEY` | 불필요 | `LLM_PROVIDER=stub` |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | 불필요 | `LLM_PROVIDER=stub` |

등록은 `gh secret set <NAME>`으로 한다. 값을 대화형 프롬프트로 입력받으므로 셸 히스토리에 남지 않는다. 명령줄에 값을 직접 넣는 형태(`gh secret set NAME --body "..."`)는 사용하지 않는다.

워크플로에서는 `secrets` 컨텍스트로 주입하고, 로그 마스킹을 신뢰하지 말고 시크릿을 `echo`하는 스텝을 만들지 않는다.

### 6.5 재발 방지

CI에 **gitleaks**를 추가한다. 시크릿이 커밋되면 파이프라인이 실패한다.

### 6.6 유출 키 폐기 (수동)

코드 작업과 별개로 반드시 선행해야 한다. 체크리스트로 관리한다.

- [ ] Google AI Studio에서 노출된 `GOOGLE_API_KEY` / `GEMINI_API_KEY` revoke
- [ ] OpenAI 콘솔에서 노출된 `OPENAI_API_KEY` revoke
- [ ] MySQL root 비밀번호 교체
- [ ] JWT secret 신규 생성 (256bit 이상)
- [ ] ArangoDB 비밀번호 교체

## 7. 테스트 · CI 골격

### 7.1 원칙

테스트는 기능과 함께 자란다. A에서는 **green 기준선**만 확보하고, 실제 테스트는 B·C·D·E에서 해당 기능과 함께 작성한다. 커버리지 백필은 하지 않는다.

### 7.2 서비스별 러너

| 대상 | 러너 | smoke test |
|---|---|---|
| `services/*` (Python 4개) | pytest + httpx | `/health` 200 + 응답 스키마 준수 |
| `apps/api` | 기존 JUnit 유지 | 컨텍스트 로딩 + `/actuator/health` |
| `apps/web` | vitest + testing-library | 렌더 1개 |

`services/xray-rag/pytest.ini`가 가리키는 `tests` 디렉터리를 실제로 생성한다.

### 7.3 CI 파이프라인 (GitHub Actions)

```
lint+build+test    workspace별 병렬
gitleaks           시크릿 재유입 차단
compose-e2e        전체 기동 후 E2E 1개
```

### 7.4 E2E 시나리오

HTTP 레벨로 구현한다. 브라우저 E2E(Playwright)는 무겁고 flaky하므로 E단계로 미룬다.

```
1. DOCTOR 로그인
2. 환자 검색
3. 진료 시작
4. 상병 등록
5. AI 처방 추천 호출 (LLM_PROVIDER=stub)
6. 응답 스키마 검증 + engineStatus == "stub" 확인

7. RECEPTIONIST 로그인
8. AI 추천 호출 → 403 확인
9. access_audit_log에 outcome=DENIED 행 생성 확인
```

권한 거부를 E2E에 포함하는 근거: RBAC은 "되는 것"보다 **"안 되는 것"을 검증해야** 의미가 있다.

### 7.5 compose 의존성 완화

현재 `spring-boot`가 8개 서비스의 `healthy`를 전부 대기하므로 하나만 실패해도 전체가 기동하지 않는다. CI에서 이는 곧바로 flaky의 원인이 된다.

변경:
- 필수 인프라(MySQL, Redis, RabbitMQ, ArangoDB)만 `condition: service_healthy` 유지
- AI 서비스(xraygraph, certificate-api, prescription-api, validation-agent)는 대기 조건 제거
- Spring은 AI 서비스 호출 실패 시 명확한 오류를 반환하고 계속 동작한다(graceful degradation)

## 8. 완료 조건

전부 실행해서 확인 가능한 항목으로만 구성한다.

1. 새 monorepo 클론 후 `docker compose up` 한 번으로 전체 기동
2. 모델 가중치 없이 CI green (mock 경로 통과)
3. 인증 없이 환자 API 호출 → `401`
4. `RECEPTIONIST` 토큰으로 AI 추천 호출 → `403`, `access_audit_log`에 `DENIED` 행 생성
5. 환자 조회 1회 → `access_audit_log`에 actor·target·IP 기록
6. gitleaks 통과
7. 유출 키 5종 폐기 완료 (6.6 체크리스트)
8. 기존 6개 repo GitHub archive 처리
9. X-ray·처방 응답에 `engineStatus` 필드 노출, 프론트에 경고 배지 표시
10. `LLM_PROVIDER=stub`으로 E2E 통과

## 9. 위험과 완화

| 위험 | 완화 |
|---|---|
| 경로 변경(`Back-End`→`apps/api`)이 문서·스크립트·compose 전반을 깨뜨림 | 이동을 단일 커밋으로 처리하고, 직후 전체 기동으로 검증. grep으로 잔존 경로 참조 확인 |
| 인증 활성화가 기존 프론트 호출을 전부 깨뜨림 | 프론트 API 클라이언트에 쿠키 전송(`withCredentials`) 일괄 적용을 같은 단계에서 처리 |
| stub provider가 실제 응답 형태와 달라 E2E가 거짓 통과 | stub 응답을 실제 응답 스키마로 검증. 스키마는 기존 Pydantic 모델 재사용 |
| SQUID 가중치 GitHub Release 업로드 시 용량 초과 | 단일 파일 2GB 한도, `model.pth`는 204MB로 여유 있음 |
| A 스코프가 B·D 영역으로 번짐 | 3.3 제외 목록과 3.4 예외 2건을 기준선으로 사용. 목록에 없으면 A가 아님 |

## 10. 다음 단계

A 완료 후 B(Grounding/Verification 레이어)로 진행한다. B의 핵심 목표는 처방 추천 출력을 실제 근거·처방 마스터와 대조하는 검증 단계를 신설하고, 그 효과를 `LLM_PROVIDER=stub` 기반으로 측정 가능하게 만드는 것이다.
