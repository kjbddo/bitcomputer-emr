# 런북: DR 스택 (AI 없는 3-tier)

## 0. 무엇을 위한 것인가

재해 복구 시나리오는 **AI 없이 3-tier 만 새로 세우는 것**이다.

진료 기록을 읽고 쓰는 것은 병원이 멈추면 안 되는 일이고, 처방 추천과 X-ray
분석은 그렇지 않다. 후자를 빼면 복구해야 할 것이 프론트·API·DB 셋으로 줄고,
받아야 할 이미지도 크게 준다.

| | 전체 스택 | DR 스택 |
|---|---|---|
| 서비스 | 12개 | **4개** |
| 이미지 총량 | 14.4GB | **약 4.5GB** |
| 외부 LLM 의존 | 있음 | **없음** |

빠지는 것:

```
prescription-api  certificate-api  validation-agent
llm-gateway       xraygraph        flask-radiology     <- AI 서비스 6개
rabbitmq          arangodb  arango-init                <- AI 전용 미들웨어
```

`rabbitmq` 는 검증 job 큐 전용이고, `arangodb` 는 처방 그래프와 X-ray 그래프
전용이다. **참고로 Spring 쪽 Arango 리포지토리는 AI 를 켜 둔 지금도 아무도
쓰지 않는다** — 그래프는 `prescription-api` 가 직접 붙는다.

`redis` 는 남긴다. 세션과 헬스체크에 실제로 쓰인다.

---

## 1. 무엇으로 갈리는가

플래그 하나다.

| 위치 | 값 | 효과 |
|---|---|---|
| `features.ai.enabled` | Spring 속성 | AI 엔드포인트 503, RabbitMQ·ArangoDB 배선 비활성 |
| `NEXT_PUBLIC_AI_FEATURES_ENABLED` | 웹 **빌드 인자** | AI 버튼을 렌더하지 않음 |

**둘 다 기본값이 "켜짐" 이다.** 설정 실수 하나로 AI 가 조용히 사라지면 화면에서
DR 구성과 구별되지 않는다. 끄는 것은 명시적 선택이어야 한다.

> **`NEXT_PUBLIC_` 값은 빌드 시점에 번들에 박힌다.** 기동 환경변수만 바꿔서는
> 프론트가 바뀌지 않는다. 그래서 DR 프론트는 **별도 이미지**이고, compose 가
> `build args` 로 넘긴다. "환경변수 넣었는데 버튼이 그대로"는 이것 때문이다.

---

## 2. 기동

```bash
cd infra
docker compose -f docker-compose.dr.yml -p bitcomputer-dr up -d --build
```

**`-p bitcomputer-dr` 를 빼면 안 된다.** 프로젝트 이름이 같으면 기존 스택과
컨테이너·볼륨·네트워크를 공유해 덮어쓴다.

포트는 전체 스택과 겹치지 않게 옮겼다. DR 검증을 평소 스택과 나란히 돌릴 수
있어야 하기 때문이다.

| 서비스 | 전체 스택 | DR |
|---|---|---|
| frontend | 3000 | **3001** |
| spring-boot | 8080 | **8081** |
| mysql | 3306 | **3308** |
| redis | 6379 | **6380** |

> `3307` 이 아니라 `3308` 인 이유: 환경에 따라 Docker Desktop 백엔드가 3307 을
> 쓴다. `DR_MYSQL_PORT` 로 바꿀 수 있다.

---

## 3. 확인

```bash
docker compose -f docker-compose.dr.yml -p bitcomputer-dr ps
```

4개 전부 `(healthy)` 여야 한다. **`frontend` 도 healthy 다** — 전체 스택과 달리
DR compose 는 헬스체크를 붙였다. DR 은 사람이 브라우저로 보고 있지 않을 때
세우는 것이라 오케스트레이터가 스스로 판단할 수 있어야 한다.

```bash
curl -s http://localhost:8081/actuator/health   # {"status":"UP"}
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3001/api/health   # 200
```

**`/actuator/health` 가 UP 인 것이 이 스택의 핵심 확인이다.** RabbitMQ 도
ArangoDB 도 없는데 UP 이어야 한다.

> `management.health.rabbit.enabled=false` 를 빠뜨리면 여기서 걸린다.
> `RabbitTemplate` 은 지연 연결이라 기동은 되는데, 헬스 인디케이터는 실제로
> 브로커에 붙어 보고 DOWN 을 낸다. 그러면 compose healthcheck 가 실패해
> 컨테이너가 unhealthy 로 남는다 — **애플리케이션은 정상인데 오케스트레이터만
> 고장으로 읽는 상태**가 된다.

---

## 4. 데이터

DR 스택은 **자기 볼륨(`dr-mysql-data`)을 쓴다.** 전체 스택 데이터를 건드리지
않는다.

빈 DB 로 뜨므로 마스터 코드를 넣어야 진료가 시작된다:

```bash
cd apps/api
MYSQL_PASSWORD="$(grep '^MYSQL_ROOT_PASSWORD=' ../../infra/.env | cut -d= -f2-)" \
  MYSQL_PORT=3308 python scripts/import_master_codes.py
```

**그래프·X-ray 적재는 하지 않는다.** ArangoDB 가 없다.
[07-runbook-data-loading.md](07-runbook-data-loading.md) 의 §3 만 해당하고
§4·§5 는 건너뛴다.

---

## 5. 화면에서 무엇이 다른가

AI 버튼 자리에 이 문구가 뜬다:

```
이 배포에는 AI 기능이 포함되어 있지 않습니다(DR 구성).
```

**버튼만 지우지 않은 이유:** 지우기만 하면 "원래 없는 기능" 처럼 보인다.
축소 구성이라는 사실 자체를 남겨야 사용자가 전체 스택을 찾아갈 수 있다.

살아 있는 것: 로그인, 환자 접수, 진료 기록, 상병·처방 입력, 진단서 **조회**,
과거 처방 조회.

죽은 것: AI 처방 추천, 진단서 **생성**, X-ray 분석.

---

## 6. CI 가 지키는 것

`.github/workflows/ci.yml` 의 `dr` 잡이 매 PR 마다 확인한다.

```
Spring 이 RabbitMQ·ArangoDB 없이 뜨는가
/actuator/health 가 UP 인가
프론트 /api/health 가 200 인가
AI 엔드포인트가 404·500 이 아닌가
DR 프로젝트에 정확히 4개 서비스만 있는가
```

**이 잡이 없으면 Spring 에 Rabbit 의존이 하나 늘어도 DR 이 필요한 날에야 알게
된다.** 재해 복구는 그때 처음 시험하는 절차가 되면 안 된다.

503 이라는 **계약 자체**는 CI 가 아니라 단위 테스트(`AiFeaturesTest`)가 지킨다.
CI 에서 그것을 확인하려면 CSRF 를 포함한 로그인을 셸로 흉내 내야 하는데, 그러면
계약이 그대로여도 인증이 바뀌면 깨지는 검사가 된다.

---

## 7. 정리

```bash
cd infra
docker compose -f docker-compose.dr.yml -p bitcomputer-dr down      # 볼륨 보존
docker compose -f docker-compose.dr.yml -p bitcomputer-dr down -v   # 데이터까지
```

---

## 8. 자주 겪는 함정

**프론트 AI 버튼이 그대로 보인다.** `NEXT_PUBLIC_` 은 빌드 시점 값이다.
`--build` 없이 올렸거나 기존 이미지를 재사용한 것이다.

**`frontend` 가 unhealthy 인데 브라우저는 열린다.** 헬스체크가 `wget` 을 쓰면
그렇게 된다 — 이 이미지에는 `wget` 도 `curl` 도 없다(`node:*-slim`). compose 는
`node -e fetch(...)` 를 쓴다.

**포트 충돌.** `3307` 은 환경에 따라 Docker Desktop 이 쓴다. `DR_MYSQL_PORT`
로 옮긴다.

**전체 스택이 같이 뜬다.** `-p bitcomputer-dr` 를 빠뜨린 것이다.
