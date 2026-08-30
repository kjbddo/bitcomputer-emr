# 런북: 컨테이너 이미지 빌드와 배포

이 저장소가 만드는 이미지들, 언제 다시 빌드해야 하는지, 어떻게 확인하는지, 레지스트리에 올리는 절차.

데이터 적재는 이 문서가 아니라 [07-runbook-data-loading.md](07-runbook-data-loading.md) 다. 두 문서는 독립이다 — 이미지를 새로 빌드해도 데이터는 볼륨에 남고, 데이터를 다시 적재해도 이미지는 그대로다.

---

## 0. 이 문서가 답하는 질문

**"코드를 고쳤는데 화면이 그대로다."**

compose 는 소스를 마운트하지 않는다. 전부 이미지에 굽는다. `docker compose up -d` 는 이미지가 이미 있으면 **다시 빌드하지 않고 그대로 띄운다.** 그래서 코드를 고치고 `up -d` 만 하면 아무 일도 일어나지 않는다 — 에러 없이, 옛 코드가 계속 돈다.

실제로 이 저장소에서 겪었다. 검증층을 다 구현하고 브라우저를 열었는데 배지가 하나도 안 보였다. 원인은 `frontend`·`spring-boot`·`validation-agent` 이미지가 이틀 전 것이었다는 것뿐이었다.

**확인하는 법:**

```bash
docker images --format "{{.Repository}}\t{{.CreatedAt}}" | grep "^infra-"
```

각 이미지의 빌드 시각을 해당 서비스의 마지막 커밋 시각과 비교한다:

```bash
for p in apps/web apps/api services/validation-agent services/prescription services/llm-gateway services/xray-rag services/radiology-legacy; do
  printf "%-28s %s\n" "$p" "$(git log -1 --format='%ad %h' --date=format:'%m-%d %H:%M' -- "$p")"
done
```

이미지가 커밋보다 오래됐으면 그 서비스는 옛 코드로 돌고 있다.

---

## 1. 이미지 목록

빌드되는 이미지 8개, 받아오는 이미지 4개.

### 빌드하는 것

| compose 서비스 | 빌드 컨텍스트 | 베이스 | 포트 | 크기 |
|---|---|---|---|---|
| `spring-boot` | `apps/api` | `eclipse-temurin:23-jdk` → `23-jre` | 8080 | 608MB |
| `frontend` | `apps/web` | `node:22-slim` (3단계) | 3000 | 1.72GB |
| `llm-gateway` | `services/llm-gateway` | `python:3.11-slim` | 8003 | 259MB |
| `prescription-api` | `services/prescription` | `python:3.11-slim` | 8001 | 565MB |
| `certificate-api` | `services/prescription` | `python:3.11-slim` | 5001 | 565MB |
| `validation-agent` | `services/validation-agent` | `python:3.11-slim` | 8002 | 366MB |
| `xraygraph` | `services/xray-rag` | `python:3.11-slim` | 8000 | 8.13GB |
| `flask-radiology` | `services/radiology-legacy` | `python:3.11-slim` | 5000 | 9.69GB |

두 가지가 눈에 띈다.

**`certificate-api` 와 `prescription-api` 는 같은 Dockerfile·같은 컨텍스트에서 나온다.** 구분은 compose 의 `command:` 뿐이다 — 하나는 `certificate_api:app` 을 5001 에, 다른 하나는 `prescription_api:app` 을 8001 에 띄운다. 즉 **565MB 짜리 같은 내용의 이미지가 두 개** 존재한다. `services/prescription` 의 코드를 고치면 **둘 다** 다시 빌드해야 한다. 한쪽만 빌드하는 실수가 잦다.

**`xraygraph` 와 `flask-radiology` 가 전체의 대부분이다.** 둘이 17.8GB 로, 빌드 이미지 총량의 83% 다. 원인은 `torch` + `torchvision` 이다. 이 둘을 건드리지 않았다면 빌드 대상에서 빼는 것만으로 빌드 시간과 디스크가 크게 줄어든다.

### 받아오는 것

| 이미지 | 용도 |
|---|---|
| `mysql:8` | 업무 DB |
| `redis:7-alpine` | 세션·캐시 |
| `rabbitmq:3-management` | 검증 작업 큐 |
| `arangodb:3.12` | 처방 추천 그래프, X-ray 그래프 |

`arango-init` 은 별도 이미지가 아니라 `arangodb:3.12` 로 DB 를 만들고 즉시 종료하는 일회성 컨테이너다. `docker ps -a` 에서 `Exited (0)` 이면 정상이다.

---

## 2. 빌드

### 전체

```bash
cd infra && docker compose build
```

빈 캐시에서는 오래 걸린다 — torch 두 개 때문이다. 처음이 아니라면 대개 바꾼 것만 빌드하면 된다.

### 바꾼 것만

```bash
cd infra && docker compose build frontend spring-boot validation-agent certificate-api prescription-api
```

캐시가 따뜻하면 이 다섯 개가 몇 분이면 끝난다. `xraygraph`·`flask-radiology` 를 뺀 이유는 위 §1 이다.

**어느 서비스를 빌드해야 하는지는 코드 경로가 정한다:**

| 고친 곳 | 다시 빌드할 서비스 |
|---|---|
| `apps/web` | `frontend` |
| `apps/api` | `spring-boot` |
| `services/prescription` | `prescription-api` **와** `certificate-api` |
| `services/validation-agent` | `validation-agent` |
| `services/llm-gateway` | `llm-gateway` |
| `services/xray-rag` | `xraygraph` |
| `services/radiology-legacy` | `flask-radiology` |

### 빌드하면서 띄우기

```bash
cd infra && docker compose up -d --build <서비스...>
```

`--build` 를 빼면 기존 이미지를 그대로 쓴다. §0 의 함정이 정확히 이것이다.

---

## 3. 기동과 확인

```bash
cd infra && docker compose up -d
docker ps --format "{{.Names}}\t{{.Status}}" | sort
```

`bit-frontend` 는 healthcheck 가 없어 `Up` 만 뜬다. 나머지 11개가 `(healthy)` 여야 한다.

```bash
for u in "3000|" "8080|/actuator/health" "8001|/health" "8002|/health" "8003|/health" "5001|/health"; do
  port=${u%%|*}; path=${u##*|}
  printf "%-6s %s\n" "$port" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "http://localhost:$port$path")"
done
```

| 포트 | 서비스 | 기대 |
|---|---|---|
| 3000 | frontend | `307` (로그인 리다이렉트) |
| 8080 | spring-boot | `200` |
| 8001 | prescription-api | `200` |
| 8002 | validation-agent | `200` |
| 8003 | llm-gateway | `200` |
| 5001 | certificate-api | `200` |

전부 healthy 인데 화면이 비어 있으면 이미지 문제가 아니라 데이터 문제다 — [07-runbook-data-loading.md](07-runbook-data-loading.md) 로 간다.

---

## 4. `.env` 는 빌드가 아니라 기동에 쓰인다

compose 는 `infra/.env` 를 읽어 컨테이너 환경변수를 만든다. **이미지에는 들어가지 않는다.** 그래서 `.env` 를 고쳤을 때는 다시 빌드할 필요 없이 재기동만 하면 된다:

```bash
cd infra && docker compose up -d <서비스>
```

`.env` 문법이 깨지면 **모든 compose 명령이 실패한다.** 실제로 겪은 사례:

```
failed to read infra/.env: line 8: unexpected character "─" in variable name
```

주석 헤더가 두 줄로 잘려 두 번째 줄이 `#` 없이 시작한 것이 원인이었다. 문법 확인은 이걸로 한다:

```bash
cd infra && docker compose config --services >/dev/null && echo OK
```

키를 추가·삭제할 때는 같은 커밋에서 `.env.example` 도 고친다. 비밀값은 `KEY=` 로 비워 두고, 노출돼도 되는 값은 실제 기본값을 적는다. 두 파일의 키가 어긋나면:

```bash
diff <(grep -oE '^[A-Z_]+=' infra/.env | tr -d '=' | sort) \
     <(grep -oE '^[A-Z_]+=' infra/.env.example | tr -d '=' | sort)
```

`<` 로 표시된 줄이 `.env` 에만 있는 키다. 그건 다른 환경에서 조용히 빠진다.

---

## 5. CI 는 전부 빌드하지 않는다

`.github/workflows/ci.yml` 의 `compose e2e` 잡은 일곱 개만 띄운다:

```
mysql redis rabbitmq arangodb arango-init prescription-api spring-boot
```

`xraygraph`·`flask-radiology` 는 torch 때문에, `certificate-api`·`validation-agent`·`frontend` 는 E2E 경로(로그인 → 환자 → 상병 → AI 처방 추천)에 관여하지 않아 제외한다. **GitHub 러너 디스크가 14GB 라 전체를 빌드할 수 없다.**

그래서 **CI green 이 "모든 이미지가 빌드된다"를 뜻하지 않는다.** `xraygraph` 나 `flask-radiology` 의 Dockerfile 을 고쳤다면 로컬에서 직접 빌드해 확인해야 한다. CI 는 그 실패를 잡지 못한다.

CI 는 `.env.example` 을 복사해 `.env` 를 만들고 비밀값만 GitHub Secrets 에서 덮어쓴다. **`.env.example` 에 키가 빠지면 CI 에서 그 값이 조용히 없는 채로 돈다.**

---

## 6. 레지스트리에 올리기 (ECR)

> **이 절은 이 저장소에서 실행 검증되지 않았다.** 작성 시점에 AWS 세션이 만료돼 있었고, 레지스트리에 실제로 push 해 보지 않았다. 계정 ID·리전·리포지터리 이름은 각자 환경에 맞춰 확인하고 쓴다.

목표 아키텍처는 ECS 다 — 서비스별 태스크 구성은 [AWS Architecture.md](AWS%20Architecture.md) 의 서비스 배치표를 본다. 이 저장소에는 IaC(Terraform, ECS 태스크 정의 등)가 없다.

로그인:

```bash
aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin <계정ID>.dkr.ecr.ap-northeast-2.amazonaws.com
```

리포지터리는 이미지마다 하나씩 필요하다. 없으면 만든다:

```bash
aws ecr create-repository --repository-name bitcomputer/prescription-api --region ap-northeast-2
```

태그와 push:

```bash
REGISTRY=<계정ID>.dkr.ecr.ap-northeast-2.amazonaws.com
TAG=$(git rev-parse --short HEAD)

docker tag infra-prescription-api:latest "$REGISTRY/bitcomputer/prescription-api:$TAG"
docker push "$REGISTRY/bitcomputer/prescription-api:$TAG"
```

**태그를 `latest` 로만 쓰지 않는다.** 커밋 SHA 로 태그하면 어떤 이미지가 어떤 코드인지 사후에 확인할 수 있다. §0 의 "이미지가 코드보다 오래됐다" 문제가 배포 환경에서 재현되면 `latest` 만으로는 진단이 불가능하다.

주의할 것:

- **`certificate-api` 와 `prescription-api` 는 내용이 같은 별개 이미지다.** 하나의 리포지터리에 올리고 ECS 태스크 정의에서 `command` 로 나누면 저장 비용과 push 시간이 절반이 된다. compose 가 둘로 나눠 빌드한다고 해서 레지스트리에서도 나눠야 하는 것은 아니다.
- **`xraygraph`·`flask-radiology` 는 각각 8~10GB 다.** push 시간과 ECR 저장 비용이 다른 이미지들과 자릿수가 다르다. torch 를 CPU 전용 휠로 바꾸거나 멀티스테이지로 빌드 의존을 걷어내면 크게 줄어든다.
- **이미지에 비밀값을 굽지 않는다.** 자격증명은 전부 런타임 환경변수로 들어간다(§4). ECS 에서는 Secrets Manager 또는 SSM Parameter Store 를 태스크 정의에 연결한다.

---

## 7. 디스크

이 스택은 디스크를 많이 쓴다. 현재 측정값:

```
Images          26.73GB
Build Cache     25.44GB  (회수 가능 21.3GB)
Local Volumes    3.58GB
```

**빌드 캐시가 이미지 총량과 맞먹는다.** 안전하게 회수하는 순서:

```bash
docker builder prune              # 빌드 캐시만. 이미지·볼륨·데이터 안 건드림
docker image prune                # 태그 없는 dangling 이미지
```

**볼륨은 함부로 지우지 않는다.** 아래 여섯 개가 이 프로젝트의 데이터다:

```
infra_mysql-data      infra_arango-data     infra_arango-apps
infra_images-storage  infra_xray-storage    infra_rabbitmq-data
```

`docker compose down` 은 볼륨을 지우지 않는다. **`docker compose down -v` 는 지운다** — 그러면 [07-runbook-data-loading.md](07-runbook-data-loading.md) 를 처음부터 다시 돌려야 하고, CheXpert 는 10.7GB 를 다시 받아야 한다.

---

## 8. 로그

```bash
docker compose logs -f <서비스>
docker compose logs --tail 100 <서비스>
```

컨테이너가 기동 직후 죽으면 `docker ps` 에 안 보인다. 종료된 것까지 봐야 한다:

```bash
docker ps -a --format "{{.Names}}\t{{.Status}}" | sort
docker logs <컨테이너이름> --tail 30
```

`Exited (0)` 은 정상 종료다 — `bit-arango-init` 은 항상 이 상태다. `Exited (1)`·`Exited (137)`(OOM)·`Exited (143)`(SIGTERM)이 조사 대상이다.

---

## 9. 자주 겪는 함정 요약

- **`up -d` 는 다시 빌드하지 않는다.** 코드를 고쳤으면 `--build` 를 붙이거나 `build` 를 먼저 돌린다
- **`services/prescription` 은 이미지 두 개를 만든다.** 한쪽만 빌드하면 다른 쪽이 옛 코드로 남는다
- **CI green ≠ 모든 이미지가 빌드된다.** CI 는 여덟 개 중 두 개만 빌드한다
- **`.env` 문법이 깨지면 모든 compose 명령이 죽는다.** `docker compose config --services` 로 먼저 확인한다
- **`.env` 는 이미지가 아니라 컨테이너에 들어간다.** 고쳤으면 재기동만 하면 되고, 다시 빌드할 필요 없다
- **`down -v` 는 데이터를 지운다.** `down` 은 안 지운다
- **전부 healthy 인데 화면이 비어 있으면** 이미지가 아니라 데이터 문제다
