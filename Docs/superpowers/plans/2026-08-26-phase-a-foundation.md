# Phase A 기반 정비 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BitComputer를 단일 monorepo로 통합하고, 인증·RBAC·감사 로그를 복구하며, 이후 모든 개선을 증명할 수 있는 테스트·CI 골격을 세운다.

**Architecture:** 기존 6개 저장소를 `apps/` + `services/` + `packages/` 구조의 단일 저장소로 옮긴다(이동만, 재작성 없음). Spring Boot에 이미 존재하나 연결되지 않은 JWT·RBAC 자산을 배선하고, HttpOnly 쿠키 기반 인증으로 전환한 뒤 환자 데이터 접근에 감사 로그를 붙인다. CI에서 실제 LLM 호출 없이 전체 경로를 검증하기 위해 결정론적 `stub` LLM provider를 추가한다.

**Tech Stack:** Java 23 / Spring Boot 3.5.6 / Spring Security / jjwt 0.11.5 / MySQL 8 / Redis 7 / RabbitMQ 3 / ArangoDB 3.12 / Python 3.11 / FastAPI / Next.js 15.5.4 / React 19.1.0 / Docker Compose / GitHub Actions

**참조 spec:** `Docs/superpowers/specs/2026-08-26-phase-a-foundation-design.md`

## Global Constraints

이 절의 항목은 모든 태스크의 요구사항에 암묵적으로 포함된다.

- **Java toolchain 23**, Spring Boot 3.5.6. `build.gradle`의 `JavaLanguageVersion.of(23)`을 변경하지 않는다.
- **Python 3.11** (`python:3.11-slim`). 모든 서비스 Dockerfile 공통.
- **JWT 서명 알고리즘은 `SignatureAlgorithm.HS512`.** 키는 최소 512bit(64바이트)여야 한다. 기존 코드가 HS512를 쓰므로 알고리즘을 바꾸지 않는다.
- **AI 로직을 변경하지 않는다.** 처방 추천·X-ray·ValidationAgent의 추론/프롬프트/스코어링 코드는 이동만 한다. 예외는 Task 4(`stub` provider)와 Task 5(`engineStatus`) 두 개뿐이며, 둘 다 기존 로직에 분기·필드만 추가한다.
- **시크릿을 커밋하지 않는다.** 실제 키·비밀번호가 파일에 들어가는 순간 Task 13의 gitleaks가 CI를 깨뜨린다.
- **`.env` 변경 시 같은 커밋에서 `.env.example`을 갱신한다.** 모든 키를 같은 순서로 유지한다.
- **응답 필드 명명은 기존 관례를 따른다.** Spring/FastAPI 응답은 camelCase(`predictedDiseases`, `engineStatus`), FastAPI 요청 본문은 snake_case(`disease_codes`, `patient_id`)를 쓴다. 기존 코드가 이 혼용 상태이므로 새로 통일하지 않는다.
- **커밋 메시지는 conventional commit prefix + 한국어 본문**을 쓴다 (기존 이력 관례: `fix: 진료정보 대시보드 api 연결`).

---

## File Structure

### 새로 만드는 파일

| 경로 | 책임 |
|---|---|
| `.gitignore` | 루트 통합 무시 규칙 (`.env`, `models/`, `node_modules/`, `.venv/`, 빌드 산출물) |
| `scripts/fetch-models.sh` | 매니페스트 기준 모델 가중치 다운로드·체크섬 검증 |
| `scripts/models.manifest.tsv` | `경로 <TAB> SHA256 <TAB> URL` 목록 |
| `infra/.env.example` | 전 서비스 환경변수 단일 원본 |
| `apps/api/.../config/JwtProperties.java` | `JWT_SECRET` 바인딩 + 부팅 시 길이 검증 |
| `apps/api/.../config/AuditInterceptor.java` | `@AuditPatientAccess` 대상 요청 기록 |
| `apps/api/.../annotation/AuditPatientAccess.java` | 감사 대상 표시 애너테이션 |
| `apps/api/.../entity/AccessAuditLog.java` | 감사 로그 엔티티 |
| `apps/api/.../Repository/AccessAuditLogRepository.java` | 감사 로그 저장소 |
| `apps/api/.../controller/AuditLogController.java` | 감사 로그 조회 (SUPER_USER 전용) |
| `apps/api/.../config/RestAccessDeniedHandler.java` | 403 응답 + 감사 기록 |
| `services/prescription/llm_provider.py` | LLM provider 팩토리 (`real` / `stub`) |
| `services/validation-agent/app/llm_provider.py` | 동일 |
| `services/*/tests/test_smoke.py` | 서비스별 헬스·스키마 smoke |
| `apps/web/vitest.config.ts` | 프론트 테스트 러너 설정 |
| `.github/workflows/ci.yml` | lint/build/test + gitleaks + compose E2E |
| `tests/e2e/test_core_flow.py` | 핵심 경로 + 권한 거부 E2E |

### 수정하는 파일

| 경로 | 변경 내용 |
|---|---|
| `apps/api/.../config/SecurityConfig.java` | `permitAll()` 제거, JWT 필터 등록, RBAC 매핑, CSRF 활성화, CORS 환경변수화 |
| `apps/api/.../jwt/JwtTokenProvider.java` | role claim 추가, 만료 8시간, 키 길이 검증 위임 |
| `apps/api/.../jwt/JwtAuthenticationFilter.java` | 하드코딩 우회 경로 목록 제거, 쿠키에서 토큰 추출, 권한 부여 |
| `apps/api/.../controller/UserController.java` | 로그인 시 HttpOnly 쿠키 발급, 로그아웃 시 쿠키 삭제 |
| `apps/api/.../serviceImpl/UserServiceImpl.java` | 토큰 생성에 role 전달 |
| `apps/web/src/lib/auth/token.ts` | localStorage 저장 제거 |
| `apps/web/src/services/http/interceptors.ts` | Authorization 헤더 주입 제거, CSRF 헤더 설정 |
| `services/xray-rag/app/models/schemas.py` | `InferenceResponse.engineStatus` 추가 |
| `services/prescription/prescription_api.py` | `engineStatus` 추가, provider 팩토리 사용 |
| `infra/docker-compose.yml` | AI 서비스 `healthy` 대기 제거, `LLM_PROVIDER` 전달 |

---

## Task 1: monorepo 초기화 및 소스 이전

**Files:**
- Create: `.gitignore`
- Move: `Back-End/` → `apps/api/`, `Front-End/` → `apps/web/`, `XrayGraphRAG/` → `services/xray-rag/`, `GraphDB/langchain_graph_qa/` → `services/prescription/`, `ValidationAgent/` → `services/validation-agent/`, `AI_BackEnd/` → `services/radiology-legacy/`, `GraphDB/data_normalize/` → `packages/graph-etl/`, `docker-compose.yml` → `infra/docker-compose.yml`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: 이후 모든 태스크가 사용하는 디렉터리 레이아웃. 경로 상수: `apps/api`, `apps/web`, `services/xray-rag`, `services/prescription`, `services/validation-agent`, `services/radiology-legacy`, `packages/graph-etl`, `infra/`

- [ ] **Step 1: 하위 저장소가 원격과 동기화됐는지 확인**

`.git` 디렉터리를 지우기 전에 미push 커밋이 없는지 반드시 확인한다. 되돌릴 수 없는 작업이다.

```bash
for d in AI_BackEnd Back-End Front-End GraphDB ValidationAgent XrayGraphRAG; do
  printf "%-16s unpushed=%s dirty=%s\n" "$d" \
    "$(git -C $d log --oneline @{u}..HEAD 2>/dev/null | wc -l)" \
    "$(git -C $d status --porcelain 2>/dev/null | wc -l)"
done
```

Expected: 모든 행이 `unpushed=0`. `dirty`가 0이 아니면 해당 저장소에서 커밋 후 push하고 다시 실행한다.

**`unpushed`가 0이 아닌 저장소가 하나라도 있으면 여기서 멈추고 push부터 한다.** 다음 단계에서 로컬 이력이 사라진다.

- [ ] **Step 2: 루트 `.gitignore` 작성**

```bash
cat > .gitignore <<'EOF'
# secrets
.env
.env.*
!.env.example

# model weights (scripts/fetch-models.sh 로 내려받는다)
models/
*.pt
*.pth

# node
node_modules/
.next/
.yarn/
*.tsbuildinfo

# python
__pycache__/
*.py[cod]
.venv/
.pytest_cache/

# java
build/
.gradle/
bin/

# runtime artifacts
storage/
generated/

# editor / os
.idea/
.vscode/
.DS_Store
EOF
```

- [ ] **Step 3: 디렉터리 구조 생성**

```bash
mkdir -p apps services packages infra scripts tests/e2e
```

- [ ] **Step 4: 소스 이동 (하위 `.git` 제외)**

`git mv`는 하위 저장소 경계를 넘지 못하므로 일반 `mv`를 쓴다. 이동 후 각 하위 `.git`을 제거한다.

```bash
mv Back-End              apps/api
mv Front-End             apps/web
mv XrayGraphRAG          services/xray-rag
mv ValidationAgent       services/validation-agent
mv AI_BackEnd            services/radiology-legacy
mv GraphDB/langchain_graph_qa services/prescription
mv GraphDB/data_normalize     packages/graph-etl
mv docker-compose.yml    infra/docker-compose.yml

rm -rf apps/api/.git apps/web/.git services/xray-rag/.git \
       services/validation-agent/.git services/radiology-legacy/.git \
       GraphDB
```

- [ ] **Step 5: 커밋된 시크릿 제거, 가중치는 저장소 밖으로 대피**

시크릿 파일은 값이 이미 폐기 대상이므로 삭제한다. **가중치는 삭제하지 않고 저장소 밖으로 옮긴다** — Task 2에서 이 파일들의 SHA256을 계산하고 GitHub Release에 업로드해야 한다. 지우면 복구할 수 없다.

```bash
# 시크릿: 삭제
rm -f services/validation-agent/evals/.env
rm -f services/prescription/.env
rm -f services/xray-rag/.env
rm -f .env.docker

# 가중치: 저장소 밖으로 대피 (Task 2 에서 사용한다)
BACKUP="$HOME/bitcomputer-model-backup"
mkdir -p "$BACKUP"
mv services/radiology-legacy/utils/CheXmask-Database-main/Weights "$BACKUP/CheXmask-Weights"
mv services/radiology-legacy/squid_exp1_256_mask "$BACKUP/squid_exp1_256_mask"

# 빌드 산출물·의존성: 삭제
rm -rf apps/web/node_modules apps/web/.next services/xray-rag/.venv
rm -rf apps/api/build apps/api/.gradle services/xray-rag/storage
```

대피 확인:

```bash
ls -la "$HOME/bitcomputer-model-backup/squid_exp1_256_mask/"
ls "$HOME/bitcomputer-model-backup/CheXmask-Weights/"
```

Expected: `model.pth`(약 204MB), `discriminator.pth`(약 2.8MB), CheXmask `Weights` 하위 디렉터리들.

`squid_exp1_256_mask`에는 `config.py`, `squid.py`, `discriminator.py`, `tools.py` 같은 **코드 파일도 함께 있다.** 이것들은 저장소에 남아야 하므로 되돌린다.

```bash
mkdir -p services/radiology-legacy/squid_exp1_256_mask
cp "$BACKUP/squid_exp1_256_mask"/*.py services/radiology-legacy/squid_exp1_256_mask/
ls services/radiology-legacy/squid_exp1_256_mask/
```

Expected: `config.py`, `discriminator.py`, `squid.py`, `tools.py` — `.pth` 파일은 없다.

- [ ] **Step 6: 잔존 경로 참조 확인**

옛 디렉터리 이름을 참조하는 곳을 찾는다.

```bash
grep -rn "Back-End\|Front-End\|XrayGraphRAG\|AI_BackEnd\|ValidationAgent\|langchain_graph_qa\|data_normalize" \
  --include='*.yml' --include='*.yaml' --include='*.properties' \
  --include='*.json' --include='*.sh' --include='*.py' --include='*.md' \
  . | grep -v '^./Docs/'
```

Expected: `infra/docker-compose.yml`의 `context:` 항목들과 `apps/api/src/main/resources/application.properties`의 `ai.prescription-agent.embed.working-directory`가 나온다.

- [ ] **Step 7: compose 빌드 컨텍스트 경로 수정**

`infra/docker-compose.yml`이 `infra/` 하위로 내려갔으므로 컨텍스트가 한 단계 위를 가리켜야 한다.

```bash
cd infra
sed -i \
  -e 's|context: ./AI_BackEnd|context: ../services/radiology-legacy|' \
  -e 's|context: ./GraphDB/langchain_graph_qa|context: ../services/prescription|' \
  -e 's|context: ./ValidationAgent|context: ../services/validation-agent|' \
  -e 's|context: ./XrayGraphRAG|context: ../services/xray-rag|' \
  -e 's|context: ./Back-End|context: ../apps/api|' \
  -e 's|context: ./Front-End|context: ../apps/web|' \
  docker-compose.yml
cd ..
grep -n "context:" infra/docker-compose.yml
```

Expected: 6개 행 모두 `../`로 시작한다.

- [ ] **Step 7b: `xray-rag/app/config.py`의 옛 경로 수정**

`Settings`의 두 기본값이 옛 디렉터리 이름을 가리킨다.

```bash
grep -n 'XrayGraphRAG\|AI_BackEnd' services/xray-rag/app/config.py
```

Expected: `STORAGE_DIR`(`"XrayGraphRAG" / "storage"`)와 `SQUID_MODEL_DIR`(`"AI_BackEnd" / "squid_exp1_256_mask"`) 두 곳.

아래처럼 바꾼다. `SQUID_MODEL_DIR`은 Task 2에서 만들 `models/` 경로를 가리킨다.

```python
    # Storage
    STORAGE_DIR: Path = Path(os.environ.get("STORAGE_DIR", str(PROJECT_ROOT / "services" / "xray-rag" / "storage")))
```

```python
    # SQUID 모델 폴더. 가중치는 scripts/fetch-models.sh 로 내려받는다.
    SQUID_MODEL_DIR: Path = Path(
        os.environ.get(
            "SQUID_MODEL_DIR",
            str(PROJECT_ROOT / "services" / "radiology-legacy" / "models" / "squid_exp1_256_mask"),
        )
    )
```

`PROJECT_ROOT`가 `parents[2]`로 계산되는데, 이동 후에도 `services/xray-rag/app/config.py` 기준 `parents[2]`는 저장소 루트다(`app` → `xray-rag` → `services` → 루트가 아니라 `parents[2]`가 `services`). 확인한다.

```bash
cd services/xray-rag && python -c "from app.config import Settings; print(Settings.PROJECT_ROOT)"; cd ../..
```

Expected: 저장소 루트 절대경로. `services`가 출력되면 `parents[2]`를 `parents[3]`으로 바꾼다.

- [ ] **Step 8: Spring의 embed working-directory 경로 수정**

```bash
sed -i 's|ai.prescription-agent.embed.working-directory=../GraphDB/langchain_graph_qa|ai.prescription-agent.embed.working-directory=../../services/prescription|' \
  apps/api/src/main/resources/application.properties
grep -n "embed.working-directory" apps/api/src/main/resources/application.properties
```

Expected: `ai.prescription-agent.embed.working-directory=../../services/prescription`

- [ ] **Step 9: 구조 검증**

```bash
ls apps services packages infra scripts
test -d apps/api/src/main/java && echo "api OK"
test -f services/prescription/prescription_api.py && echo "prescription OK"
test -f services/xray-rag/app/main.py && echo "xray OK"
test -f services/validation-agent/app/agent.py && echo "validation OK"
test -f infra/docker-compose.yml && echo "compose OK"
test ! -d apps/api/.git && echo "nested git removed"
```

Expected: `api OK`, `prescription OK`, `xray OK`, `validation OK`, `compose OK`, `nested git removed` 6줄 모두 출력.

- [ ] **Step 10: 커밋**

```bash
git add -A
git commit -m "refactor: 6개 저장소를 monorepo 구조로 통합" -m "Back-End -> apps/api, Front-End -> apps/web,
XrayGraphRAG -> services/xray-rag, langchain_graph_qa -> services/prescription,
ValidationAgent -> services/validation-agent, AI_BackEnd -> services/radiology-legacy,
data_normalize -> packages/graph-etl.

커밋되어 있던 .env 파일과 모델 가중치를 제거하고 루트 .gitignore를 추가."
```

---

## Task 2: 모델 가중치 외부화

**Files:**
- Create: `scripts/models.manifest.tsv`
- Create: `scripts/fetch-models.sh`
- Modify: `services/radiology-legacy/config.py`

**Interfaces:**
- Consumes: Task 1의 디렉터리 레이아웃
- Produces: `scripts/fetch-models.sh` — 인자 없이 실행하면 매니페스트의 모든 항목을 받아 체크섬 검증. 실패 시 exit 1.

- [ ] **Step 1: 대피시킨 가중치의 SHA256 수집**

Task 1 Step 5에서 `$HOME/bitcomputer-model-backup`으로 옮겨둔 파일을 쓴다.

```bash
BACKUP="$HOME/bitcomputer-model-backup"
sha256sum \
  "$BACKUP/squid_exp1_256_mask/model.pth" \
  "$BACKUP/squid_exp1_256_mask/discriminator.pth" \
  "$BACKUP/CheXmask-Weights/SegmentationModel/bestMSE.pt"
```

Expected: 각 파일의 64자 hex 해시 3줄. 이 값을 다음 단계 매니페스트에 넣는다.

백업 디렉터리가 없다면 Task 1 Step 5를 건너뛴 것이다. 원본은 GitHub의 `PatboongIsBetterthanSyuboong/AI_BackEnd`에 남아 있으므로 거기서 받는다.

```bash
git clone --depth 1 https://github.com/PatboongIsBetterthanSyuboong/AI_BackEnd.git /tmp/ai-backend-recover
```

- [ ] **Step 2: 매니페스트 작성**

`<로컬경로> <TAB> <SHA256> <TAB> <URL>` 형식이다. URL은 SQUID 가중치를 GitHub Release로 올린 뒤의 asset 주소를 쓴다.

```bash
cat > scripts/models.manifest.tsv <<'EOF'
# path	sha256	url
services/radiology-legacy/models/squid_exp1_256_mask/model.pth	REPLACE_WITH_SHA256	https://github.com/kjbddo/bitcomputer/releases/download/models-v1/model.pth
services/radiology-legacy/models/squid_exp1_256_mask/discriminator.pth	REPLACE_WITH_SHA256	https://github.com/kjbddo/bitcomputer/releases/download/models-v1/discriminator.pth
services/radiology-legacy/models/CheXmask/SegmentationModel/bestMSE.pt	REPLACE_WITH_SHA256	https://github.com/ngaggion/CheXmask-Database/raw/main/Weights/SegmentationModel/bestMSE.pt
EOF
```

두 곳을 실제 값으로 바꾼다. 치환하지 않으면 Step 4가 실패한다.

1. `REPLACE_WITH_SHA256` 세 곳 → Step 1에서 얻은 해시
2. Release URL의 `kjbddo/bitcomputer` → 실제 새 monorepo의 `<owner>/<repo>`

저장소 이름을 아직 정하지 않았다면 지금 정한다. 확인:

```bash
gh repo view --json nameWithOwner -q .nameWithOwner
```

- [ ] **Step 3: 다운로드 스크립트 작성**

```bash
cat > scripts/fetch-models.sh <<'EOF'
#!/usr/bin/env bash
# 매니페스트 기준으로 모델 가중치를 내려받고 SHA256을 검증한다.
set -euo pipefail

MANIFEST="$(dirname "$0")/models.manifest.tsv"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail=0
while IFS=$'\t' read -r path sha url; do
  case "$path" in ''|\#*) continue ;; esac

  dest="$ROOT/$path"
  mkdir -p "$(dirname "$dest")"

  if [ -f "$dest" ] && [ "$(sha256sum "$dest" | cut -d' ' -f1)" = "$sha" ]; then
    echo "ok (cached)  $path"
    continue
  fi

  echo "downloading  $path"
  if ! curl -fsSL --retry 3 -o "$dest" "$url"; then
    echo "FAILED download: $path" >&2
    fail=1
    continue
  fi

  actual="$(sha256sum "$dest" | cut -d' ' -f1)"
  if [ "$actual" != "$sha" ]; then
    echo "FAILED checksum: $path" >&2
    echo "  expected $sha" >&2
    echo "  actual   $actual" >&2
    rm -f "$dest"
    fail=1
    continue
  fi
  echo "ok           $path"
done < "$MANIFEST"

exit "$fail"
EOF
chmod +x scripts/fetch-models.sh
```

- [ ] **Step 4: 스크립트 실행 검증**

```bash
./scripts/fetch-models.sh
echo "exit=$?"
```

Expected: 각 항목에 `ok` 또는 `ok (cached)`, 마지막에 `exit=0`.

Release asset을 아직 올리지 않았다면 SQUID 두 항목이 `FAILED download`로 나온다. 그 경우 먼저 업로드한다:

```bash
gh release create models-v1 --title "Model weights v1" --notes "SQUID anomaly model weights"
gh release upload models-v1 ~/backup/squid_exp1_256_mask/model.pth ~/backup/squid_exp1_256_mask/discriminator.pth
```

- [ ] **Step 5: 서비스가 새 경로를 읽도록 수정**

`services/radiology-legacy/config.py`에서 가중치 디렉터리를 환경변수로 받되 기본값을 새 경로로 둔다.

```bash
grep -n "squid_exp1_256_mask\|MODEL_DIR\|model.pth" services/radiology-legacy/config.py
```

찾은 경로 상수를 아래 형태로 바꾼다.

```python
import os
from pathlib import Path

MODEL_DIR = Path(os.environ.get(
    "SQUID_MODEL_DIR",
    Path(__file__).resolve().parent / "models" / "squid_exp1_256_mask",
))
```

- [ ] **Step 6: 커밋**

```bash
git add scripts/models.manifest.tsv scripts/fetch-models.sh services/radiology-legacy/config.py
git commit -m "feat: 모델 가중치를 저장소 밖으로 분리" -m "매니페스트 기반 다운로드 스크립트와 SHA256 검증을 추가하고,
가중치 경로를 SQUID_MODEL_DIR 환경변수로 받도록 변경."
```

---

## Task 3: 시크릿 통합과 fail-fast 검증

**Files:**
- Create: `infra/.env.example`
- Create: `services/prescription/env_check.py`
- Create: `services/validation-agent/app/env_check.py`
- Create: `services/xray-rag/app/env_check.py`
- Modify: `services/prescription/prescription_api.py`, `services/validation-agent/app/main.py`, `services/xray-rag/app/main.py`
- Modify: `apps/api/src/main/resources/application.properties`

**Interfaces:**
- Consumes: Task 1의 레이아웃
- Produces: `require_env(names: list[str]) -> None` — 누락 변수가 있으면 `SystemExit(1)`. 세 Python 서비스가 동일 시그니처로 각자 보유한다(서비스 간 import 의존을 만들지 않기 위해 복제한다).

- [ ] **Step 1: `.env.example` 작성**

```bash
cat > infra/.env.example <<'EOF'
# ── Database ─────────────────────────────────────────────
MYSQL_ROOT_PASSWORD=
MYSQL_DATABASE=bitcomputer
MYSQL_USER=root
MYSQL_PASSWORD=

# ── ArangoDB ─────────────────────────────────────────────
ARANGO_PASSWORD=
ARANGO_DATABASE=bitcomputer_graph
XRAY_ARANGO_DATABASE=xray_graph_db

# ── RabbitMQ ─────────────────────────────────────────────
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=
RABBITMQ_ERLANG_COOKIE=

# ── Auth ─────────────────────────────────────────────────
# HS512 서명에 쓰이므로 64바이트 이상이어야 한다.
#   openssl rand -base64 64
JWT_SECRET=
# 쉼표로 구분한 허용 Origin 목록
CORS_ALLOWED_ORIGINS=http://localhost:3000

# ── LLM ──────────────────────────────────────────────────
# real | stub   (stub 은 결정론적 고정 응답. CI/테스트용)
LLM_PROVIDER=real
GOOGLE_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
OPENAI_MODEL=gpt-5-nano

# ── X-ray engine ─────────────────────────────────────────
# xray | flask
RADIOLOGY_ENGINE=xray
# AP | PA
XRAY_API_DEFAULT_VIEW=PA
USE_TORCH_ANOMALY=false
USE_TORCH_EMBEDDING=false

# ── Front-End ────────────────────────────────────────────
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
EOF
```

- [ ] **Step 2: 실패하는 테스트 작성 (prescription)**

```bash
mkdir -p services/prescription/tests
cat > services/prescription/tests/test_env_check.py <<'EOF'
import pytest

from env_check import require_env


def test_passes_when_all_present(monkeypatch):
    monkeypatch.setenv("FOO_A", "1")
    monkeypatch.setenv("FOO_B", "2")
    require_env(["FOO_A", "FOO_B"])


def test_exits_when_missing(monkeypatch, capsys):
    monkeypatch.delenv("FOO_MISSING", raising=False)
    with pytest.raises(SystemExit) as exc:
        require_env(["FOO_MISSING"])
    assert exc.value.code == 1
    assert "FOO_MISSING" in capsys.readouterr().err


def test_exits_when_blank(monkeypatch, capsys):
    monkeypatch.setenv("FOO_BLANK", "   ")
    with pytest.raises(SystemExit) as exc:
        require_env(["FOO_BLANK"])
    assert exc.value.code == 1
    assert "FOO_BLANK" in capsys.readouterr().err
EOF
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```bash
cd services/prescription && python -m pytest tests/test_env_check.py -v; cd ../..
```

Expected: FAIL — `ModuleNotFoundError: No module named 'env_check'`

- [ ] **Step 4: 최소 구현**

```bash
cat > services/prescription/env_check.py <<'EOF'
"""필수 환경변수 검증. 누락 시 즉시 종료한다."""
from __future__ import annotations

import os
import sys
from typing import Iterable


def require_env(names: Iterable[str]) -> None:
    missing = [n for n in names if not (os.environ.get(n) or "").strip()]
    if not missing:
        return
    print(
        "필수 환경변수가 설정되지 않았습니다: " + ", ".join(missing) + "\n"
        "infra/.env.example 을 참고해 infra/.env 를 채우세요.",
        file=sys.stderr,
    )
    raise SystemExit(1)
EOF
```

- [ ] **Step 5: 테스트가 통과하는지 확인**

```bash
cd services/prescription && python -m pytest tests/test_env_check.py -v; cd ../..
```

Expected: PASS 3개

- [ ] **Step 6: 나머지 두 서비스에 복제**

서비스 간 import 의존을 만들지 않기 위해 같은 파일을 각자 둔다.

```bash
cp services/prescription/env_check.py services/validation-agent/app/env_check.py
cp services/prescription/env_check.py services/xray-rag/app/env_check.py
```

- [ ] **Step 7: 각 서비스 기동 시 호출**

`services/prescription/prescription_api.py`의 `app = FastAPI(...)` 직전에 추가한다. `LLM_PROVIDER=stub`이면 API 키가 필요 없으므로 조건부로 검사한다.

```python
from env_check import require_env

_required = ["ARANGO_PASSWORD"]
if os.environ.get("LLM_PROVIDER", "real") != "stub":
    _required.append("GOOGLE_API_KEY")
require_env(_required)
```

`services/validation-agent/app/main.py`의 FastAPI 인스턴스 생성 직전:

```python
import os

from .env_check import require_env

_required: list[str] = []
if os.environ.get("LLM_PROVIDER", "real") != "stub":
    _required.append("OPENAI_API_KEY")
require_env(_required)
```

`services/xray-rag/app/main.py`의 FastAPI 인스턴스 생성 직전:

```python
from app.env_check import require_env

require_env(["ARANGO_PASSWORD"])
```

- [ ] **Step 8: Spring의 JWT secret 하드코딩 제거**

```bash
sed -i 's|^jwt.secret=.*|jwt.secret=${JWT_SECRET}|' \
  apps/api/src/main/resources/application.properties
sed -i 's|^jwt.secret=.*|jwt.secret=${JWT_SECRET}|' \
  apps/api/src/main/resources/application-local.properties
grep -n "^jwt.secret" apps/api/src/main/resources/application*.properties
```

Expected: 두 파일 모두 `jwt.secret=${JWT_SECRET}`

- [ ] **Step 9: CORS origin 환경변수 추가**

```bash
cat >> apps/api/src/main/resources/application.properties <<'EOF'

# CORS 허용 Origin (쉼표 구분)
cors.allowed-origins=${CORS_ALLOWED_ORIGINS:http://localhost:3000}
EOF
```

- [ ] **Step 10: fail-fast 동작 확인**

```bash
cd services/xray-rag && ARANGO_PASSWORD= python -c "from app.env_check import require_env; require_env(['ARANGO_PASSWORD'])"; echo "exit=$?"; cd ../..
```

Expected: stderr에 `필수 환경변수가 설정되지 않았습니다: ARANGO_PASSWORD`, `exit=1`

- [ ] **Step 11: 커밋**

```bash
git add infra/.env.example services/*/env_check.py services/*/app/env_check.py \
        services/prescription/tests/test_env_check.py \
        services/prescription/prescription_api.py \
        services/validation-agent/app/main.py services/xray-rag/app/main.py \
        apps/api/src/main/resources/application.properties \
        apps/api/src/main/resources/application-local.properties
git commit -m "feat: 시크릿을 .env.example 하나로 통합하고 fail-fast 검증 추가" -m "필수 환경변수가 비어 있으면 서비스가 조용히 뜨는 대신 즉시 종료한다.
JWT secret 하드코딩을 제거하고 CORS Origin을 환경변수로 뺐다."
```

---

## Task 4: `LLM_PROVIDER=stub` 모드

**Files:**
- Create: `services/prescription/llm_provider.py`
- Create: `services/prescription/tests/test_llm_provider.py`
- Create: `services/validation-agent/app/llm_provider.py`
- Modify: `services/prescription/prescription_api.py:570-590` (LLM 호출부)
- Modify: `services/validation-agent/app/agent.py:201-207` (`_create_llm`)

**Interfaces:**
- Consumes: Task 3의 `require_env`
- Produces:
  - `services/prescription/llm_provider.py`: `resolve_provider() -> str` (`"real"` | `"stub"`), `stub_prescription_response(top_rx: Any) -> str` — `parse_prescriptions_llm_response`가 파싱 가능한 JSON 문자열을 반환
  - `services/validation-agent/app/llm_provider.py`: `resolve_provider() -> str`, `stub_tool_decision(iteration: int) -> dict` — `{"thought": str, "action": str, "actionInput": dict}` 반환

- [ ] **Step 1: 실패하는 테스트 작성**

stub 응답이 기존 파서를 통과해야 한다. 이게 핵심 계약이다.

```bash
cat > services/prescription/tests/test_llm_provider.py <<'EOF'
import json

from llm_provider import resolve_provider, stub_prescription_response
from prescription_agent import parse_prescriptions_llm_response


def test_resolve_provider_defaults_to_real(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert resolve_provider() == "real"


def test_resolve_provider_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert resolve_provider() == "stub"


def test_stub_response_parses_with_real_parser():
    top_rx = [
        {"처방명": "아목시실린캡슐", "처방코드": "A001"},
        {"처방명": "타이레놀정", "처방코드": "B002"},
    ]
    raw = stub_prescription_response(top_rx)
    data = parse_prescriptions_llm_response(raw)
    assert len(data["prescriptions"]) == 3
    assert [p["rank"] for p in data["prescriptions"]] == [1, 2, 3]


def test_stub_response_uses_codes_from_input():
    top_rx = [{"처방명": "아목시실린캡슐", "처방코드": "A001"}]
    data = json.loads(stub_prescription_response(top_rx))
    assert data["prescriptions"][0]["prescription_code"] == "A001"


def test_stub_response_is_deterministic():
    top_rx = [{"처방명": "아목시실린캡슐", "처방코드": "A001"}]
    assert stub_prescription_response(top_rx) == stub_prescription_response(top_rx)


def test_stub_response_handles_empty_input():
    data = json.loads(stub_prescription_response([]))
    assert data["prescriptions"][0]["prescription_code"] == "미기재"
EOF
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/prescription && python -m pytest tests/test_llm_provider.py -v; cd ../..
```

Expected: FAIL — `ModuleNotFoundError: No module named 'llm_provider'`

- [ ] **Step 3: 최소 구현**

```bash
cat > services/prescription/llm_provider.py <<'EOF'
"""LLM provider 선택.

stub 은 결정론적 고정 응답을 돌려준다. CI 와 grounding 평가에서 LLM 출력을
고정하기 위한 것이며, 임상적 의미는 없다.
"""
from __future__ import annotations

import json
import os
from typing import Any

STUB_MARKER = "STUB: 고정 응답이며 임상 근거가 없습니다."


def resolve_provider() -> str:
    value = (os.environ.get("LLM_PROVIDER") or "real").strip().lower()
    return "stub" if value == "stub" else "real"


def _row_name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("처방명", "prescription_name", "name"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _row_code(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("처방코드", "prescription_code", "code"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def stub_prescription_response(top_rx: Any) -> str:
    """parse_prescriptions_llm_response 가 파싱 가능한 JSON 문자열을 만든다."""
    rows = top_rx if isinstance(top_rx, list) else []
    picked = [r for r in rows if _row_name(r) or _row_code(r)][:3]

    items = []
    for rank in (1, 2, 3):
        row = picked[rank - 1] if rank <= len(picked) else None
        items.append({
            "rank": rank,
            "name": _row_name(row) or "데이터 부족: top_rx 비어 있음",
            "prescription_code": _row_code(row) or "미기재",
            "dosage": "미기재",
            "reason": STUB_MARKER,
        })
    return json.dumps({"prescriptions": items}, ensure_ascii=False)
EOF
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd services/prescription && python -m pytest tests/test_llm_provider.py -v; cd ../..
```

Expected: PASS 6개

- [ ] **Step 5: `prescription_api.py`의 LLM 호출부에 분기 추가**

`try:` 블록 안 `if _is_openai_model(model_id):` 바로 앞에 stub 분기를 넣는다. 기존 호출 로직은 그대로 둔다.

```python
    try:
        if resolve_provider() == "stub":
            raw = stub_prescription_response(effective_top_rx)
            trace_tool("llm_generate", True, status="success", model="stub", temperature=0.0)
        elif _is_openai_model(model_id):
            raw = _invoke_openai_json(model_id, temperature, SYSTEM_PRESCRIPTION, user_msg)
        else:
            llm = ChatGoogleGenerativeAI(model=model_id, temperature=temperature)
            resp = llm.invoke([
                ("system", SYSTEM_PRESCRIPTION),
                ("human", user_msg),
            ])
            raw = (resp.content or "").strip() if hasattr(resp, "content") else str(resp).strip()
```

파일 상단 import 구역에 추가한다.

```python
from llm_provider import resolve_provider, stub_prescription_response
```

기존 `trace_tool("llm_generate", ...)` 호출이 `elif`/`else` 분기 뒤에 한 번 더 있으므로, stub 분기에서만 별도 기록하고 공통 기록은 그대로 둔다. 중복 기록은 `eval_trace_enabled`가 켜졌을 때만 발생하며 무해하다.

- [ ] **Step 6: validation-agent provider 작성**

```bash
cat > services/validation-agent/app/llm_provider.py <<'EOF'
"""LLM provider 선택 (ValidationAgent).

stub 은 결정론적 도구 선택 순서를 돌려준다. CI 에서 OpenAI 호출 없이
ReAct 루프를 통과시키기 위한 것이며, 임상적 의미는 없다.
"""
from __future__ import annotations

import os
from typing import Any, Dict

STUB_SEQUENCE = [
    "X-ray Result Loader",
    "Disease Validator",
    "Prescription Validator",
    "FINALIZE",
]


def resolve_provider() -> str:
    value = (os.environ.get("LLM_PROVIDER") or "real").strip().lower()
    return "stub" if value == "stub" else "real"


def stub_tool_decision(iteration: int) -> Dict[str, Any]:
    """iteration 은 1부터 시작한다."""
    index = max(0, iteration - 1)
    action = STUB_SEQUENCE[index] if index < len(STUB_SEQUENCE) else "FINALIZE"
    return {
        "thought": f"STUB 결정 {iteration}: {action}",
        "action": action,
        "actionInput": {},
    }
EOF
```

- [ ] **Step 7: `_decide_next_tool`에 stub 분기 추가**

`services/validation-agent/app/agent.py`의 `_decide_next_tool` 함수 본문 첫 줄에 넣는다.

```python
def _decide_next_tool(
    state: ValidationState,
    reasoning_trace: List[Dict[str, Any]],
    pubmed_queries: List[str],
    iteration: int,
) -> Dict[str, Any]:
    if resolve_provider() == "stub":
        return stub_tool_decision(iteration)
```

파일 상단 import 구역에 추가한다.

```python
from .llm_provider import resolve_provider, stub_tool_decision
```

- [ ] **Step 8: compose에 `LLM_PROVIDER` 전달**

`infra/docker-compose.yml`의 `prescription-api`, `certificate-api`, `validation-agent` 세 서비스 `environment` 블록에 각각 추가한다.

```yaml
      LLM_PROVIDER: ${LLM_PROVIDER:-real}
```

- [ ] **Step 9: 커밋**

```bash
git add services/prescription/llm_provider.py services/prescription/tests/test_llm_provider.py \
        services/prescription/prescription_api.py \
        services/validation-agent/app/llm_provider.py services/validation-agent/app/agent.py \
        infra/docker-compose.yml
git commit -m "feat: LLM_PROVIDER=stub 모드 추가" -m "결정론적 고정 응답 provider 를 주입 지점에 추가한다. 기존 LLM 호출 로직은
변경하지 않고 분기만 넣었다. CI 에서 실제 LLM 키 없이 AI 경로를 통과시키고,
이후 grounding 검증의 효과 측정에 사용한다."
```

---

## Task 5: `engineStatus` 정직성 필드

**Files:**
- Modify: `services/xray-rag/app/models/schemas.py:108-116`
- Modify: `services/xray-rag/app/services/case_service.py`
- Create: `services/xray-rag/tests/test_engine_status.py`
- Modify: `services/prescription/prescription_api.py` (`PrescriptionRecommendResponse`)
- Modify: `apps/web/src/components/AIReport.tsx`

**Interfaces:**
- Consumes: Task 4의 `resolve_provider`
- Produces:
  - `services/xray-rag/app/config.py`: `Settings.engine_status() -> str` — `USE_TORCH_ANOMALY`와 `USE_TORCH_EMBEDDING`이 모두 참이면 `"real"`, 아니면 `"mock"`
  - `InferenceResponse.engineStatus: str`
  - `PrescriptionRecommendResponse.engineStatus: str`

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
mkdir -p services/xray-rag/tests
cat > services/xray-rag/tests/test_engine_status.py <<'EOF'
from app.config import Settings


def test_mock_when_both_toggles_off(monkeypatch):
    monkeypatch.setenv("USE_TORCH_ANOMALY", "false")
    monkeypatch.setenv("USE_TORCH_EMBEDDING", "false")
    assert Settings().engine_status() == "mock"


def test_mock_when_only_one_toggle_on(monkeypatch):
    monkeypatch.setenv("USE_TORCH_ANOMALY", "true")
    monkeypatch.setenv("USE_TORCH_EMBEDDING", "false")
    assert Settings().engine_status() == "mock"


def test_real_when_both_toggles_on(monkeypatch):
    monkeypatch.setenv("USE_TORCH_ANOMALY", "true")
    monkeypatch.setenv("USE_TORCH_EMBEDDING", "true")
    assert Settings().engine_status() == "real"
EOF
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd services/xray-rag && python -m pytest tests/test_engine_status.py -v; cd ../..
```

Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'engine_status'`

- [ ] **Step 3: `Settings.engine_status()` 구현**

`services/xray-rag/app/config.py`의 `Settings` 클래스 안에 추가한다.

`Settings`의 필드는 클래스 변수라서 모듈 import 시점에 `os.environ`을 한 번만 읽는다. `Settings()`를 새로 만들어도 재평가되지 않으므로, `engine_status`는 `os.environ`을 직접 읽어야 테스트가 통과한다.

```python
    def engine_status(self) -> str:
        """실행 중인 추론 엔진이 실제 모델인지 mock 인지 알린다.

        USE_TORCH_ROI 는 실 어댑터가 없어(factory 가 항상 MockROIModel 을 쓴다)
        판정에서 제외한다.

        클래스 변수는 import 시점에 고정되므로 여기서는 os.environ 을 직접 읽는다.
        """
        anomaly = _bool(os.environ.get("USE_TORCH_ANOMALY"), False)
        embedding = _bool(os.environ.get("USE_TORCH_EMBEDDING"), False)
        return "real" if (anomaly and embedding) else "mock"
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd services/xray-rag && python -m pytest tests/test_engine_status.py -v; cd ../..
```

Expected: PASS 3개

- [ ] **Step 5: 응답 스키마에 필드 추가**

`services/xray-rag/app/models/schemas.py`의 `InferenceResponse`에 추가한다.

```python
class InferenceResponse(BaseModel):
    queryCase: Dict[str, Any]
    predictedDiseases: List[PredictedDisease]
    notableFindings: List[NotableFinding]
    similarCases: List[SimilarCase]
    uncertainty: Uncertainty
    explanation: Dict[str, Any]
    heatmapPath: Optional[str] = None
    warning: str
    engineStatus: str = "mock"
```

- [ ] **Step 6: `case_service.infer`가 값을 채우도록 수정**

`services/xray-rag/app/services/case_service.py`에서 `InferenceResponse(...)`를 생성하는 지점을 찾는다.

```bash
grep -n "InferenceResponse(" services/xray-rag/app/services/case_service.py
```

해당 생성자 호출에 인자를 추가한다.

```python
            engineStatus=self.settings.engine_status(),
```

`case_service`가 `settings`를 보유하지 않으면 `__init__`에 주입한다.

- [ ] **Step 7: 처방 응답에 필드 추가**

`services/prescription/prescription_api.py`의 `PrescriptionRecommendResponse`에 추가한다.

```python
class PrescriptionRecommendResponse(BaseModel):
    prescriptions: List[PrescriptionItem]
    used_arango_top_rx: bool = False
    arango_top_rx_count: int = 0
    used_cohort_rx: bool = False
    cohort_rx_count: int = 0
    toolTrace: List[Dict[str, Any]] = []
    engineStatus: str = "real"
```

`recommend`의 `return` 문에 추가한다.

```python
    return PrescriptionRecommendResponse(
        prescriptions=items,
        used_arango_top_rx=used_arango,
        arango_top_rx_count=arango_count,
        used_cohort_rx=used_cohort,
        cohort_rx_count=cohort_count,
        toolTrace=tool_trace if eval_trace_enabled else [],
        engineStatus=resolve_provider(),
    )
```

- [ ] **Step 8: 프론트 경고 배지**

`apps/web/src/components/AIReport.tsx`에서 AI 결과를 렌더하는 지점에 추가한다. `engineStatus`가 `real`이 아닐 때만 표시한다.

```tsx
{engineStatus && engineStatus !== "real" && (
  <div
    role="status"
    style={{
      background: "#fff4e5",
      border: "1px solid #ffa726",
      borderRadius: 4,
      padding: "8px 12px",
      marginBottom: 12,
      fontSize: 13,
    }}
  >
    이 결과는 <strong>{engineStatus}</strong> 엔진에서 생성되었습니다. 실제 모델
    추론이 아니므로 임상 판단에 사용할 수 없습니다.
  </div>
)}
```

`engineStatus`를 응답 타입과 props에 추가한다. `AIReport`가 받는 결과 객체 타입에 `engineStatus?: string`을 넣는다.

- [ ] **Step 9: 커밋**

```bash
git add services/xray-rag/app/config.py services/xray-rag/app/models/schemas.py \
        services/xray-rag/app/services/case_service.py \
        services/xray-rag/tests/test_engine_status.py \
        services/prescription/prescription_api.py \
        apps/web/src/components/AIReport.tsx
git commit -m "feat: AI 응답에 engineStatus 필드와 경고 배지 추가" -m "현재 X-ray 파이프라인은 mock 모델로 동작하는데 응답에는 그 사실이 드러나지
않았다. 엔진 상태를 응답에 노출하고, real 이 아니면 프론트에 경고를 띄운다."
```

---

## Task 6: compose 의존성 완화

**Files:**
- Modify: `infra/docker-compose.yml`

**Interfaces:**
- Consumes: Task 1의 경로 수정, Task 4의 `LLM_PROVIDER`
- Produces: AI 서비스가 하나 죽어도 `spring-boot`와 `frontend`가 기동하는 compose 구성

- [ ] **Step 1: `spring-boot`의 AI 서비스 대기 조건 제거**

`infra/docker-compose.yml`의 `spring-boot.depends_on`에서 AI 서비스 4개를 뺀다. 인프라 4개만 남긴다.

```yaml
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
      arangodb:
        condition: service_healthy
      arango-init:
        condition: service_completed_successfully
```

제거 대상: `xraygraph`, `certificate-api`, `prescription-api`, `validation-agent` 네 항목.

- [ ] **Step 2: `frontend`의 대기 조건 완화**

`spring-boot`가 healthy가 될 때까지 기다리면 백엔드 기동 실패 시 프론트도 못 뜬다. `service_started`로 낮춘다.

```yaml
  frontend:
    depends_on:
      spring-boot:
        condition: service_started
```

- [ ] **Step 3: `validation-agent`의 prescription 대기 제거**

`validation-agent.depends_on`에서 `prescription-api`를 빼고 `rabbitmq`만 남긴다. 처방 API 호출은 런타임에 실패를 반환하도록 이미 `tools.py:prescription_finder`가 예외를 잡는다.

```yaml
    depends_on:
      rabbitmq:
        condition: service_healthy
```

- [ ] **Step 4: 전체 기동 검증**

```bash
cd infra
cp .env.example .env
# .env 를 채운다: MYSQL_ROOT_PASSWORD, ARANGO_PASSWORD, RABBITMQ_PASSWORD,
#                 RABBITMQ_ERLANG_COOKIE, JWT_SECRET (openssl rand -base64 64)
#                 LLM_PROVIDER=stub 로 두면 LLM 키가 필요 없다
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
cd ..
```

Expected: 모든 컨테이너 `Up`. `bit-spring-boot`, `bit-frontend` 포함.

- [ ] **Step 5: AI 서비스 중단 후에도 기동하는지 확인**

이게 이번 태스크의 핵심 검증이다.

```bash
cd infra
docker compose --env-file .env stop xraygraph prescription-api
docker compose --env-file .env restart spring-boot
sleep 30
curl -fsS http://localhost:8080/actuator/health && echo " <- spring OK"
cd ..
```

Expected: `{"status":"UP"...}` 와 `<- spring OK`. AI 서비스 2개가 내려간 상태에서도 Spring이 뜬다.

- [ ] **Step 6: 되돌리고 커밋**

```bash
cd infra && docker compose --env-file .env start xraygraph prescription-api && cd ..
git add infra/docker-compose.yml
git commit -m "fix: compose 의존성 완화로 부분 장애 시 전체 기동 실패 방지" -m "spring-boot 가 AI 서비스 4개의 healthy 를 기다리던 것을 제거했다.
하나만 죽어도 전체가 안 뜨던 문제와 CI flaky 원인을 함께 없앤다."
```

---

## Task 7: JWT 강화 (role claim, 키 검증, 만료)

**Files:**
- Create: `apps/api/src/main/java/com/example/bitcomputer/config/JwtProperties.java`
- Create: `apps/api/src/test/java/com/example/bitcomputer/jwt/JwtTokenProviderTest.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/jwt/JwtTokenProvider.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/serviceImpl/UserServiceImpl.java:67-69`

**Interfaces:**
- Consumes: Task 3의 `jwt.secret=${JWT_SECRET}`
- Produces:
  - `JwtTokenProvider.generateAccessToken(String username, Role role) -> String`
  - `JwtTokenProvider.extractRole(String token) -> Role`
  - `JwtTokenProvider.getAccessTokenValiditySeconds() -> long` (28800)
  - `JwtProperties.getSecret() -> String` — 부팅 시 64바이트 미만이면 `IllegalStateException`

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
mkdir -p apps/api/src/test/java/com/example/bitcomputer/jwt
cat > apps/api/src/test/java/com/example/bitcomputer/jwt/JwtTokenProviderTest.java <<'EOF'
package com.example.bitcomputer.jwt;

import com.example.bitcomputer.entity.Role;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.*;

class JwtTokenProviderTest {

    private static final String VALID_SECRET =
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    private JwtTokenProvider provider;

    @BeforeEach
    void setUp() {
        provider = new JwtTokenProvider();
        ReflectionTestUtils.setField(provider, "secretKey", VALID_SECRET);
        provider.init();
    }

    @Test
    void generatedTokenCarriesUsername() {
        String token = provider.generateAccessToken("dr.kim", Role.DOCTOR);
        assertEquals("dr.kim", provider.extractUsername(token));
    }

    @Test
    void generatedTokenCarriesRole() {
        String token = provider.generateAccessToken("dr.kim", Role.DOCTOR);
        assertEquals(Role.DOCTOR, provider.extractRole(token));
    }

    @Test
    void roleSurvivesForEveryRoleValue() {
        for (Role role : Role.values()) {
            String token = provider.generateAccessToken("someone", role);
            assertEquals(role, provider.extractRole(token));
        }
    }

    @Test
    void accessTokenValidityIsEightHours() {
        assertEquals(28800L, provider.getAccessTokenValiditySeconds());
    }

    @Test
    void shortSecretIsRejectedAtStartup() {
        JwtTokenProvider weak = new JwtTokenProvider();
        ReflectionTestUtils.setField(weak, "secretKey", "tooshort");
        assertThrows(IllegalStateException.class, weak::init);
    }

    @Test
    void tamperedTokenFailsValidation() {
        String token = provider.generateAccessToken("dr.kim", Role.DOCTOR);
        String tampered = token.substring(0, token.length() - 2) + "xy";
        assertFalse(provider.validateToken(tampered));
    }
}
EOF
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*JwtTokenProviderTest*'; cd ../..
```

Expected: 컴파일 실패 — `generateAccessToken(String, Role)`, `extractRole`, `getAccessTokenValiditySeconds` 미정의

- [ ] **Step 3: `JwtTokenProvider` 수정**

`apps/api/src/main/java/com/example/bitcomputer/jwt/JwtTokenProvider.java` 전체를 아래로 교체한다.

```java
package com.example.bitcomputer.jwt;

import com.example.bitcomputer.entity.Role;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.util.Date;

@Component
public class JwtTokenProvider {

    /** HS512 서명에 필요한 최소 키 길이(바이트). */
    private static final int MIN_SECRET_BYTES = 64;

    private static final long ACCESS_TOKEN_VALIDITY_SECONDS = 28800L;   // 8시간
    private static final long REFRESH_TOKEN_VALIDITY_SECONDS = 604800L; // 7일

    private static final String CLAIM_ROLE = "role";

    @Value("${jwt.secret}")
    private String secretKey;

    private Key SECRET_KEY;

    @PostConstruct
    public void init() {
        if (secretKey == null || secretKey.getBytes(StandardCharsets.UTF_8).length < MIN_SECRET_BYTES) {
            throw new IllegalStateException(
                    "jwt.secret 이 너무 짧습니다. HS512 서명에는 최소 " + MIN_SECRET_BYTES
                            + "바이트가 필요합니다. `openssl rand -base64 64` 로 생성하세요.");
        }
        this.SECRET_KEY = Keys.hmacShaKeyFor(secretKey.getBytes(StandardCharsets.UTF_8));
    }

    public long getAccessTokenValiditySeconds() {
        return ACCESS_TOKEN_VALIDITY_SECONDS;
    }

    public long getRefreshTokenValiditySeconds() {
        return REFRESH_TOKEN_VALIDITY_SECONDS;
    }

    public String generateAccessToken(String username, Role role) {
        return build(username, role, ACCESS_TOKEN_VALIDITY_SECONDS);
    }

    public String generateRefreshToken(String username) {
        return build(username, null, REFRESH_TOKEN_VALIDITY_SECONDS);
    }

    private String build(String username, Role role, long validitySeconds) {
        requireInitialized();
        long now = System.currentTimeMillis();
        var builder = Jwts.builder()
                .setSubject(username)
                .setIssuedAt(new Date(now))
                .setExpiration(new Date(now + validitySeconds * 1000L));
        if (role != null) {
            builder.claim(CLAIM_ROLE, role.name());
        }
        return builder.signWith(SECRET_KEY, SignatureAlgorithm.HS512).compact();
    }

    public boolean validateToken(String token) {
        if (SECRET_KEY == null || token == null || token.isEmpty()) {
            return false;
        }
        try {
            parse(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public String extractUsername(String token) {
        return parse(token).getSubject();
    }

    public Role extractRole(String token) {
        String raw = parse(token).get(CLAIM_ROLE, String.class);
        if (raw == null) {
            return Role.DEFAULT;
        }
        try {
            return Role.valueOf(raw);
        } catch (IllegalArgumentException e) {
            return Role.DEFAULT;
        }
    }

    public long getExpiration(String token) {
        return parse(token).getExpiration().getTime();
    }

    private Claims parse(String token) {
        requireInitialized();
        return Jwts.parserBuilder()
                .setSigningKey(SECRET_KEY)
                .build()
                .parseClaimsJws(token)
                .getBody();
    }

    private void requireInitialized() {
        if (SECRET_KEY == null) {
            throw new IllegalStateException("SECRET_KEY is not initialized. Check jwt.secret configuration.");
        }
    }
}
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*JwtTokenProviderTest*'; cd ../..
```

Expected: PASS 6개

- [ ] **Step 5: 호출부 수정**

`apps/api/src/main/java/com/example/bitcomputer/serviceImpl/UserServiceImpl.java`의 `loginUser`에서 role을 넘긴다.

```java
        String accessToken = jwtTokenProvider.generateAccessToken(
                employee.getUsername(), employee.getRole());
        String refreshToken = jwtTokenProvider.generateRefreshToken(employee.getUsername());
        return new TokenInfo("Bearer", accessToken, refreshToken);
```

- [ ] **Step 6: 다른 호출부가 없는지 확인하고 전체 빌드**

```bash
grep -rn "generateAccessToken" apps/api/src/main/java
cd apps/api && ./gradlew compileJava compileTestJava; cd ../..
```

Expected: `generateAccessToken` 호출이 `UserServiceImpl` 한 곳뿐이고, 컴파일 성공.

- [ ] **Step 7: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/jwt/JwtTokenProvider.java \
        apps/api/src/main/java/com/example/bitcomputer/serviceImpl/UserServiceImpl.java \
        apps/api/src/test/java/com/example/bitcomputer/jwt/JwtTokenProviderTest.java
git commit -m "feat: JWT 에 role claim 추가하고 secret 길이를 부팅 시 검증" -m "RBAC 에 필요한 role 을 토큰에 싣고, HS512 최소 64바이트 조건을 시작 시점에
확인한다. access token 만료를 8시간(교대 근무 1회)으로 조정."
```

---

## Task 8: HttpOnly 쿠키 기반 로그인·로그아웃

**Files:**
- Modify: `apps/api/src/main/java/com/example/bitcomputer/controller/UserController.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/config/CookieFactory.java`
- Create: `apps/api/src/test/java/com/example/bitcomputer/config/CookieFactoryTest.java`

**Interfaces:**
- Consumes: Task 7의 `JwtTokenProvider.getAccessTokenValiditySeconds()`
- Produces:
  - `CookieFactory.accessTokenCookie(String token, long maxAgeSeconds) -> ResponseCookie` — HttpOnly, SameSite=Lax, path=/
  - `CookieFactory.expiredAccessTokenCookie() -> ResponseCookie` — maxAge 0
  - 쿠키 이름 상수 `CookieFactory.ACCESS_TOKEN_COOKIE = "access_token"`
  - `POST /api/user/login` 응답에 `Set-Cookie: access_token=...; HttpOnly`

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
mkdir -p apps/api/src/test/java/com/example/bitcomputer/config
cat > apps/api/src/test/java/com/example/bitcomputer/config/CookieFactoryTest.java <<'EOF'
package com.example.bitcomputer.config;

import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseCookie;

import static org.junit.jupiter.api.Assertions.*;

class CookieFactoryTest {

    @Test
    void accessTokenCookieIsHttpOnly() {
        ResponseCookie cookie = new CookieFactory(false).accessTokenCookie("tok", 28800L);
        assertTrue(cookie.isHttpOnly());
    }

    @Test
    void accessTokenCookieUsesLaxSameSite() {
        ResponseCookie cookie = new CookieFactory(false).accessTokenCookie("tok", 28800L);
        assertEquals("Lax", cookie.getSameSite());
    }

    @Test
    void accessTokenCookieCarriesValueAndMaxAge() {
        ResponseCookie cookie = new CookieFactory(false).accessTokenCookie("tok", 28800L);
        assertEquals("access_token", cookie.getName());
        assertEquals("tok", cookie.getValue());
        assertEquals(28800L, cookie.getMaxAge().getSeconds());
    }

    @Test
    void secureFlagFollowsConfiguration() {
        assertFalse(new CookieFactory(false).accessTokenCookie("tok", 1L).isSecure());
        assertTrue(new CookieFactory(true).accessTokenCookie("tok", 1L).isSecure());
    }

    @Test
    void expiredCookieHasZeroMaxAgeAndEmptyValue() {
        ResponseCookie cookie = new CookieFactory(false).expiredAccessTokenCookie();
        assertEquals(0L, cookie.getMaxAge().getSeconds());
        assertEquals("", cookie.getValue());
    }
}
EOF
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*CookieFactoryTest*'; cd ../..
```

Expected: 컴파일 실패 — `CookieFactory` 클래스 없음

- [ ] **Step 3: `CookieFactory` 구현**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/config/CookieFactory.java <<'EOF'
package com.example.bitcomputer.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 인증 쿠키 생성기.
 *
 * access token 은 HttpOnly 로 내려 JS 가 읽지 못하게 한다. XSS 로 토큰이
 * 탈취되는 경로를 막기 위한 것이며, 프론트는 토큰 값을 알 필요가 없다.
 */
@Component
public class CookieFactory {

    public static final String ACCESS_TOKEN_COOKIE = "access_token";

    private final boolean secure;

    public CookieFactory(@Value("${auth.cookie.secure:false}") boolean secure) {
        this.secure = secure;
    }

    public ResponseCookie accessTokenCookie(String token, long maxAgeSeconds) {
        return ResponseCookie.from(ACCESS_TOKEN_COOKIE, token)
                .httpOnly(true)
                .secure(secure)
                .sameSite("Lax")
                .path("/")
                .maxAge(Duration.ofSeconds(maxAgeSeconds))
                .build();
    }

    public ResponseCookie expiredAccessTokenCookie() {
        return ResponseCookie.from(ACCESS_TOKEN_COOKIE, "")
                .httpOnly(true)
                .secure(secure)
                .sameSite("Lax")
                .path("/")
                .maxAge(Duration.ZERO)
                .build();
    }
}
EOF
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*CookieFactoryTest*'; cd ../..
```

Expected: PASS 5개

- [ ] **Step 5: `UserController`가 쿠키를 발급하도록 수정**

`apps/api/src/main/java/com/example/bitcomputer/controller/UserController.java`의 `loginUser`와 `logout`을 교체한다. 로그아웃은 헤더 대신 쿠키에서 토큰을 읽는다.

```java
    @PostMapping("/login")
    public ResponseEntity<TokenInfo> loginUser(@RequestBody LoginRequestDTO loginRequestDTO) {
        TokenInfo tokenInfo = userService.loginUser(loginRequestDTO);
        if (tokenInfo == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(null);
        }
        ResponseCookie cookie = cookieFactory.accessTokenCookie(
                tokenInfo.getAccessToken(), jwtTokenProvider.getAccessTokenValiditySeconds());
        // 응답 본문에서는 access token 을 제거한다. 쿠키로만 전달한다.
        TokenInfo body = TokenInfo.builder()
                .grantType(tokenInfo.getGrantType())
                .accessToken(null)
                .refreshToken(null)
                .build();
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(body);
    }

    @PostMapping("/logout")
    public ResponseEntity<String> logout(
            @CookieValue(value = CookieFactory.ACCESS_TOKEN_COOKIE, required = false) String token) {
        ResponseCookie expired = cookieFactory.expiredAccessTokenCookie();
        if (token != null && jwtTokenProvider.validateToken(token)) {
            userService.logoutUser(token);
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, expired.toString())
                .body("Logged out successfully");
    }
```

import와 생성자에 `CookieFactory`를 추가한다.

```java
import com.example.bitcomputer.config.CookieFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.web.bind.annotation.CookieValue;
```

```java
    private final UserService userService;
    private final JwtTokenProvider jwtTokenProvider;
    private final CookieFactory cookieFactory;

    public UserController(UserService userService, JwtTokenProvider jwtTokenProvider,
                          CookieFactory cookieFactory) {
        this.userService = userService;
        this.jwtTokenProvider = jwtTokenProvider;
        this.cookieFactory = cookieFactory;
    }
```

- [ ] **Step 6: 쿠키 secure 설정 추가**

로컬은 http라 `secure=false`, docker/운영은 true로 둔다.

```bash
cat >> apps/api/src/main/resources/application.properties <<'EOF'

# HTTPS 환경에서는 true 로 둔다
auth.cookie.secure=${AUTH_COOKIE_SECURE:false}
EOF
```

- [ ] **Step 7: 전체 빌드**

```bash
cd apps/api && ./gradlew compileJava compileTestJava; cd ../..
```

Expected: BUILD SUCCESSFUL

- [ ] **Step 8: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/config/CookieFactory.java \
        apps/api/src/test/java/com/example/bitcomputer/config/CookieFactoryTest.java \
        apps/api/src/main/java/com/example/bitcomputer/controller/UserController.java \
        apps/api/src/main/resources/application.properties
git commit -m "feat: access token 을 HttpOnly 쿠키로 전달" -m "응답 본문에서 토큰을 제거하고 HttpOnly + SameSite=Lax 쿠키로만 내린다.
JS 가 토큰을 읽을 수 없으므로 XSS 로 인한 탈취 경로가 막힌다."
```

---

## Task 9: 인증 활성화와 RBAC

**Files:**
- Modify: `apps/api/src/main/java/com/example/bitcomputer/jwt/JwtAuthenticationFilter.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java`
- Create: `apps/api/src/test/java/com/example/bitcomputer/config/SecurityConfigTest.java`

**Interfaces:**
- Consumes: Task 7의 `extractRole`, Task 8의 `CookieFactory.ACCESS_TOKEN_COOKIE`
- Produces: 인증된 요청의 `SecurityContext`에 `ROLE_<Role.name()>` 권한이 실린다. 예: `ROLE_DOCTOR`

**주의:** 현재 `JwtAuthenticationFilter`에는 `/api/patients/`, `/api/agent/`, `/api/ai/` 등을 무조건 통과시키는 하드코딩 목록이 있다. 이 목록을 지우지 않으면 `SecurityConfig`를 고쳐도 인증이 걸리지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
cat > apps/api/src/test/java/com/example/bitcomputer/config/SecurityConfigTest.java <<'EOF'
package com.example.bitcomputer.config;

import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
class SecurityConfigTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    private jakarta.servlet.http.Cookie cookieFor(Role role) {
        String token = jwtTokenProvider.generateAccessToken("tester", role);
        return new jakarta.servlet.http.Cookie(CookieFactory.ACCESS_TOKEN_COOKIE, token);
    }

    @Test
    void patientApiRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/patients/1"))
               .andExpect(status().isUnauthorized());
    }

    @Test
    void loginEndpointIsPublic() throws Exception {
        mockMvc.perform(post("/api/user/login")
                       .contentType("application/json")
                       .content("{\"username\":\"none\",\"password\":\"none\"}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(401)));
    }

    @Test
    void actuatorHealthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
               .andExpect(status().isOk());
    }

    @Test
    void receptionistCannotCallAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.RECEPTIONIST))
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    void nurseCannotCallAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.NURSE))
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    void doctorReachesAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.DOCTOR))
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void defaultRoleIsDeniedEverywhere() throws Exception {
        mockMvc.perform(get("/api/patients/1")
                       .cookie(cookieFor(Role.DEFAULT)))
               .andExpect(status().isForbidden());
    }

    @Test
    void superUserOnlyForRoleManagement() throws Exception {
        mockMvc.perform(get("/api/super/employees")
                       .cookie(cookieFor(Role.DOCTOR)))
               .andExpect(status().isForbidden());
    }
}
EOF
```

- [ ] **Step 2: 테스트 프로파일 설정 추가**

테스트가 실제 MySQL/Redis에 붙지 않도록 H2와 인메모리 설정을 쓴다.

```bash
mkdir -p apps/api/src/test/resources
cat > apps/api/src/test/resources/application-test.properties <<'EOF'
spring.datasource.url=jdbc:h2:mem:testdb;MODE=MySQL;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.sql.init.mode=never

spring.autoconfigure.exclude=\
  org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration,\
  org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration,\
  org.springframework.boot.autoconfigure.amqp.RabbitAutoConfiguration

jwt.secret=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
auth.cookie.secure=false
cors.allowed-origins=http://localhost:3000
ai.prescription-agent.embed.enabled=false
validation.scheduler.enabled=false
EOF
```

`build.gradle`의 `dependencies`에 H2를 추가한다.

```groovy
    testImplementation 'com.h2database:h2'
```

Redis를 제외하면 `TokenBlacklistService`의 `RedisTemplate` 주입이 실패하므로, 테스트용 목 빈을 둔다.

```bash
cat > apps/api/src/test/java/com/example/bitcomputer/config/TestRedisConfig.java <<'EOF'
package com.example.bitcomputer.config;

import org.mockito.Mockito;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

@TestConfiguration
public class TestRedisConfig {

    @Bean
    @SuppressWarnings("unchecked")
    public RedisTemplate<String, Object> redisTemplate() {
        RedisTemplate<String, Object> template = Mockito.mock(RedisTemplate.class);
        ValueOperations<String, Object> ops = Mockito.mock(ValueOperations.class);
        Mockito.when(template.opsForValue()).thenReturn(ops);
        Mockito.when(template.hasKey(Mockito.anyString())).thenReturn(false);
        return template;
    }
}
EOF
```

`SecurityConfigTest` 클래스 애너테이션에 추가한다.

```java
@org.springframework.context.annotation.Import(TestRedisConfig.class)
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*SecurityConfigTest*'; cd ../..
```

Expected: FAIL — `patientApiRequiresAuthentication`이 401 대신 200/404를 받는다 (현재 `permitAll()`)

- [ ] **Step 4: `JwtAuthenticationFilter` 교체**

우회 목록을 지우고, 쿠키에서 토큰을 읽고, role을 권한으로 싣는다. 인증 실패 시 여기서 응답을 쓰지 않고 Security 체인에 위임한다.

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/jwt/JwtAuthenticationFilter.java <<'EOF'
package com.example.bitcomputer.jwt;

import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.serviceImpl.TokenBlacklistService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

/**
 * 요청의 access token 을 검증해 SecurityContext 를 채운다.
 *
 * 경로별 허용 여부는 SecurityConfig 가 결정한다. 이 필터는 인증 정보를 싣기만
 * 하고, 토큰이 없거나 잘못됐으면 컨텍스트를 비운 채 통과시킨다.
 */
@Component
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtTokenProvider jwtTokenProvider;
    private final TokenBlacklistService tokenBlacklistService;

    public JwtAuthenticationFilter(JwtTokenProvider jwtTokenProvider,
                                   TokenBlacklistService tokenBlacklistService) {
        this.jwtTokenProvider = jwtTokenProvider;
        this.tokenBlacklistService = tokenBlacklistService;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {

        String token = resolveToken(request);

        if (token != null
                && jwtTokenProvider.validateToken(token)
                && !tokenBlacklistService.isBlacklisted(token)) {

            String username = jwtTokenProvider.extractUsername(token);
            Role role = jwtTokenProvider.extractRole(token);

            var authority = new SimpleGrantedAuthority("ROLE_" + role.name());
            var authentication = new UsernamePasswordAuthenticationToken(
                    username, null, List.of(authority));
            SecurityContextHolder.getContext().setAuthentication(authentication);
        }

        filterChain.doFilter(request, response);
    }

    /** 쿠키를 우선 보고, 없으면 Authorization 헤더를 본다(도구·테스트 편의). */
    private String resolveToken(HttpServletRequest request) {
        Cookie[] cookies = request.getCookies();
        if (cookies != null) {
            for (Cookie cookie : cookies) {
                if (CookieFactory.ACCESS_TOKEN_COOKIE.equals(cookie.getName())) {
                    return cookie.getValue();
                }
            }
        }
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            return header.substring(7);
        }
        return null;
    }
}
EOF
```

- [ ] **Step 5: `SecurityConfig` 교체**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java <<'EOF'
package com.example.bitcomputer.config;

import com.example.bitcomputer.jwt.JwtAuthenticationFilter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.Arrays;
import java.util.List;

@Configuration
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final String allowedOrigins;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter,
                          @Value("${cors.allowed-origins}") String allowedOrigins) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.allowedOrigins = allowedOrigins;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(cors -> cors.configurationSource(corsConfigurationSource()))
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(e -> e.authenticationEntryPoint(
                    new HttpStatusEntryPoint(org.springframework.http.HttpStatus.UNAUTHORIZED)))
            .authorizeHttpRequests(auth -> auth
                // ── 공개 ──
                .requestMatchers("/api/user/login", "/api/user/register").permitAll()
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()

                // ── SUPER_USER 전용 ──
                .requestMatchers("/api/super/**", "/api/audit/**").hasRole("SUPER_USER")

                // ── AI 기능: 임상 판단이 개입하므로 DOCTOR 전용 ──
                .requestMatchers("/api/agent/**", "/api/ai/**",
                                 "/api/validation-jobs/**", "/api/radiology/**")
                    .hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 진료 기록 작성: DOCTOR ──
                .requestMatchers(HttpMethod.POST,   "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.PUT,    "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.DELETE, "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 처방 등록·수정: DOCTOR / 조회: NURSE 도 가능 ──
                .requestMatchers(HttpMethod.POST,   "/api/history-diagnoses/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.PUT,    "/api/history-diagnoses/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.DELETE, "/api/history-diagnoses/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.GET,    "/api/history-diagnoses/**")
                    .hasAnyRole("DOCTOR", "NURSE", "SUPER_USER")

                // ── 상병 등록·수정: DOCTOR ──
                .requestMatchers(HttpMethod.POST,   "/api/history-diseases/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.PUT,    "/api/history-diseases/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.DELETE, "/api/history-diseases/**").hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 환자·대기: 원무도 가능 ──
                .requestMatchers("/api/patients/**", "/api/waiting/**")
                    .hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")

                // ── 마스터 코드 조회 ──
                .requestMatchers(HttpMethod.GET, "/api/diseases/**", "/api/diagnoses/**")
                    .hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")

                // ── 나머지 업무 API: 인증된 실제 역할이면 통과 (DEFAULT 제외) ──
                .anyRequest().hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")
            )
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of(allowedOrigins.split("\\s*,\\s*")));
        configuration.setAllowedMethods(Arrays.asList("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("*"));
        configuration.setAllowCredentials(true);
        configuration.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }
}
EOF
```

CSRF는 아직 건드리지 않는다. Task 10에서 켠다. 현재 상태는 기본값(활성)이라 POST 테스트가 403을 받을 수 있으므로, 이 태스크에서는 임시로 비활성 유지가 필요하다. `securityFilterChain`의 `.cors(...)` 다음 줄에 추가한다.

```java
            .csrf(csrf -> csrf.disable())  // Task 10 에서 CookieCsrfTokenRepository 로 교체
```

- [ ] **Step 6: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*SecurityConfigTest*'; cd ../..
```

Expected: PASS 8개

`doctorReachesAgentApi`가 500으로 실패하면 정상이다 — 권한은 통과했고 본문이 비어 서비스가 터진 것이다. 테스트는 403이 아님만 확인한다.

- [ ] **Step 7: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java \
        apps/api/src/main/java/com/example/bitcomputer/jwt/JwtAuthenticationFilter.java \
        apps/api/src/test/java/com/example/bitcomputer/config/SecurityConfigTest.java \
        apps/api/src/test/java/com/example/bitcomputer/config/TestRedisConfig.java \
        apps/api/src/test/resources/application-test.properties \
        apps/api/build.gradle
git commit -m "feat: 인증 활성화 및 역할 기반 접근제어 적용" -m "permitAll() 을 제거하고 JWT 필터를 다시 등록했다. 필터에 있던 하드코딩
우회 경로 목록(/api/patients/, /api/agent/ 등)도 함께 제거했다.
AI 엔드포인트는 임상 판단이 개입하므로 DOCTOR 전용으로 묶었다."
```

---

## Task 10: CSRF 보호

**Files:**
- Modify: `apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java`
- Modify: `apps/web/src/services/http/client.ts`
- Create: `apps/api/src/test/java/com/example/bitcomputer/config/CsrfTest.java`

**Interfaces:**
- Consumes: Task 9의 SecurityConfig
- Produces: 서버가 `XSRF-TOKEN` 쿠키(HttpOnly 아님)를 발급하고, 상태 변경 요청에 `X-XSRF-TOKEN` 헤더를 요구한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
cat > apps/api/src/test/java/com/example/bitcomputer/config/CsrfTest.java <<'EOF'
package com.example.bitcomputer.config;

import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestRedisConfig.class)
class CsrfTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    private jakarta.servlet.http.Cookie doctorCookie() {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken("dr.kim", Role.DOCTOR));
    }

    @Test
    void postWithoutCsrfTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/api/patients")
                       .cookie(doctorCookie())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfTokenPassesCsrfCheck() throws Exception {
        mockMvc.perform(post("/api/patients")
                       .cookie(doctorCookie())
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void getRequestsSkipCsrfCheck() throws Exception {
        mockMvc.perform(get("/api/patients/1").cookie(doctorCookie()))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void loginIsExemptFromCsrf() throws Exception {
        mockMvc.perform(post("/api/user/login")
                       .contentType("application/json")
                       .content("{\"username\":\"none\",\"password\":\"none\"}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }
}
EOF
```

`build.gradle`에 Spring Security 테스트 지원을 추가한다.

```groovy
    testImplementation 'org.springframework.security:spring-security-test'
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*CsrfTest*'; cd ../..
```

Expected: FAIL — `postWithoutCsrfTokenIsForbidden`이 403 대신 다른 상태를 받는다 (현재 `csrf.disable()`)

- [ ] **Step 3: CSRF 활성화**

`SecurityConfig.securityFilterChain`에서 Task 9에 넣은 `.csrf(csrf -> csrf.disable())`를 교체한다.

```java
            .csrf(csrf -> csrf
                .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
                .ignoringRequestMatchers("/api/user/login", "/api/user/register")
            )
```

import를 추가한다.

```java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
```

로그인·회원가입은 아직 CSRF 토큰을 받기 전이므로 제외한다.

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*CsrfTest*'; cd ../..
```

Expected: PASS 4개

- [ ] **Step 5: 프론트 axios에 CSRF 설정**

`apps/web/src/services/http/client.ts`의 `axios.create` 호출에 두 줄을 추가한다.

```ts
  const instance = axios.create({
    baseURL,
    timeout,
    withCredentials: true,
    xsrfCookieName: "XSRF-TOKEN",
    xsrfHeaderName: "X-XSRF-TOKEN",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
  });
```

- [ ] **Step 6: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java \
        apps/api/src/test/java/com/example/bitcomputer/config/CsrfTest.java \
        apps/api/build.gradle apps/web/src/services/http/client.ts
git commit -m "feat: CSRF 보호 활성화" -m "쿠키 기반 인증으로 전환했으므로 전면 csrf.disable() 을 해제하고
CookieCsrfTokenRepository 로 XSRF-TOKEN 을 발급한다.
프론트 axios 에 xsrfCookieName/xsrfHeaderName 을 설정했다."
```

---

## Task 11: 환자 기록 접근 감사 로그

**Files:**
- Create: `apps/api/src/main/java/com/example/bitcomputer/annotation/AuditPatientAccess.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/entity/AccessAuditLog.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/Repository/AccessAuditLogRepository.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/service/AuditService.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/config/AuditInterceptor.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/config/RestAccessDeniedHandler.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/controller/AuditLogController.java`
- Create: `apps/api/src/test/java/com/example/bitcomputer/config/AuditLogTest.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/config/WebMvcConfig.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/controller/PatientController.java`

**Interfaces:**
- Consumes: Task 9의 `SecurityContext` 권한
- Produces:
  - `AuditService.record(String action, Integer patientId, Integer historyId, String ip, String outcome, String detail) -> void`
  - `AccessAuditLogRepository.findAllByOrderByOccurredAtDesc(Pageable) -> Page<AccessAuditLog>`
  - `GET /api/audit/logs` (SUPER_USER 전용)

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
cat > apps/api/src/test/java/com/example/bitcomputer/config/AuditLogTest.java <<'EOF'
package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestRedisConfig.class)
class AuditLogTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private JwtTokenProvider jwtTokenProvider;
    @Autowired private AccessAuditLogRepository auditRepository;

    private jakarta.servlet.http.Cookie cookieFor(Role role, String username) {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken(username, role));
    }

    @BeforeEach
    void clear() {
        auditRepository.deleteAll();
    }

    @Test
    void patientLookupIsRecorded() throws Exception {
        mockMvc.perform(get("/api/patients/1").cookie(cookieFor(Role.DOCTOR, "dr.kim")));

        var logs = auditRepository.findAll();
        assertEquals(1, logs.size());
        assertEquals("dr.kim", logs.get(0).getActorUsername());
        assertEquals("DOCTOR", logs.get(0).getActorRole());
        assertEquals("GRANTED", logs.get(0).getOutcome());
        assertNotNull(logs.get(0).getRequestIp());
    }

    @Test
    void deniedAgentCallIsRecorded() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.RECEPTIONIST, "front.lee"))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"));

        var denied = auditRepository.findAll().stream()
                .filter(l -> "DENIED".equals(l.getOutcome()))
                .toList();
        assertEquals(1, denied.size());
        assertEquals("front.lee", denied.get(0).getActorUsername());
        assertEquals("RECEPTIONIST", denied.get(0).getActorRole());
    }

    @Test
    void auditLogIsReadableBySuperUserOnly() throws Exception {
        mockMvc.perform(get("/api/audit/logs").cookie(cookieFor(Role.SUPER_USER, "admin")))
               .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isOk());

        mockMvc.perform(get("/api/audit/logs").cookie(cookieFor(Role.DOCTOR, "dr.kim")))
               .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isForbidden());
    }

    @Test
    void unannotatedEndpointIsNotRecorded() throws Exception {
        mockMvc.perform(get("/api/diseases?page=0&size=5").cookie(cookieFor(Role.NURSE, "nurse.park")));
        assertTrue(auditRepository.findAll().isEmpty());
    }
}
EOF
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*AuditLogTest*'; cd ../..
```

Expected: 컴파일 실패 — `AccessAuditLogRepository`, `AccessAuditLog` 없음

- [ ] **Step 3: 애너테이션과 엔티티 작성**

```bash
mkdir -p apps/api/src/main/java/com/example/bitcomputer/annotation
cat > apps/api/src/main/java/com/example/bitcomputer/annotation/AuditPatientAccess.java <<'EOF'
package com.example.bitcomputer.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 환자 식별 정보를 다루는 엔드포인트에 붙인다.
 *
 * AOP 로 전 구간을 자동으로 감싸지 않고 명시적으로 표시하는 이유는, 어떤
 * 엔드포인트가 환자 데이터를 만지는지가 코드에 드러나게 하기 위해서다.
 * 이 애너테이션이 붙은 목록이 곧 감사 대상 문서가 된다.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditPatientAccess {
    /** 감사 로그에 남길 행위 이름. 예: PATIENT_VIEW */
    String action();
}
EOF

cat > apps/api/src/main/java/com/example/bitcomputer/entity/AccessAuditLog.java <<'EOF'
package com.example.bitcomputer.entity;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 환자 기록 접근 감사 로그.
 *
 * append-only 다. 수정·삭제 API 를 만들지 않는다.
 */
@Entity
@Table(name = "access_audit_log", indexes = {
        @Index(name = "idx_audit_occurred_at", columnList = "occurred_at"),
        @Index(name = "idx_audit_patient", columnList = "target_patient_id")
})
@Data
@NoArgsConstructor
@AllArgsConstructor
public class AccessAuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    @Column(name = "actor_username", nullable = false, length = 100)
    private String actorUsername;

    @Column(name = "actor_role", nullable = false, length = 30)
    private String actorRole;

    @Column(name = "action", nullable = false, length = 60)
    private String action;

    @Column(name = "target_patient_id")
    private Integer targetPatientId;

    @Column(name = "target_history_id")
    private Integer targetHistoryId;

    @Column(name = "request_ip", length = 64)
    private String requestIp;

    /** GRANTED | DENIED */
    @Column(name = "outcome", nullable = false, length = 16)
    private String outcome;

    @Column(name = "detail", columnDefinition = "TEXT")
    private String detail;
}
EOF
```

- [ ] **Step 4: 저장소와 서비스 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/Repository/AccessAuditLogRepository.java <<'EOF'
package com.example.bitcomputer.Repository;

import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccessAuditLogRepository extends JpaRepository<AccessAuditLog, Long> {
    Page<AccessAuditLog> findAllByOrderByOccurredAtDesc(Pageable pageable);
}
EOF

cat > apps/api/src/main/java/com/example/bitcomputer/service/AuditService.java <<'EOF'
package com.example.bitcomputer.service;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.entity.AccessAuditLog;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
public class AuditService {

    public static final String GRANTED = "GRANTED";
    public static final String DENIED = "DENIED";

    private final AccessAuditLogRepository repository;

    public AuditService(AccessAuditLogRepository repository) {
        this.repository = repository;
    }

    public void record(String action, Integer patientId, Integer historyId,
                       String ip, String outcome, String detail) {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();

        AccessAuditLog log = new AccessAuditLog();
        log.setOccurredAt(LocalDateTime.now());
        log.setActorUsername(auth != null ? String.valueOf(auth.getName()) : "anonymous");
        log.setActorRole(resolveRole(auth));
        log.setAction(action);
        log.setTargetPatientId(patientId);
        log.setTargetHistoryId(historyId);
        log.setRequestIp(ip);
        log.setOutcome(outcome);
        log.setDetail(detail);

        repository.save(log);
    }

    public String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }

    private String resolveRole(Authentication auth) {
        if (auth == null) {
            return "ANONYMOUS";
        }
        return auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(a -> a.startsWith("ROLE_"))
                .map(a -> a.substring("ROLE_".length()))
                .findFirst()
                .orElse("UNKNOWN");
    }
}
EOF
```

- [ ] **Step 5: 인터셉터 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/config/AuditInterceptor.java <<'EOF'
package com.example.bitcomputer.config;

import com.example.bitcomputer.annotation.AuditPatientAccess;
import com.example.bitcomputer.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class AuditInterceptor implements HandlerInterceptor {

    private final AuditService auditService;

    public AuditInterceptor(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (!(handler instanceof HandlerMethod method)) {
            return true;
        }
        AuditPatientAccess annotation = method.getMethodAnnotation(AuditPatientAccess.class);
        if (annotation == null) {
            return true;
        }

        auditService.record(
                annotation.action(),
                parsePathVariable(request, "patientId", "id"),
                parsePathVariable(request, "historyId"),
                auditService.clientIp(request),
                AuditService.GRANTED,
                request.getMethod() + " " + request.getRequestURI());
        return true;
    }

    @SuppressWarnings("unchecked")
    private Integer parsePathVariable(HttpServletRequest request, String... names) {
        Object attr = request.getAttribute(
                org.springframework.web.servlet.HandlerMapping.URI_TEMPLATE_VARIABLES_ATTRIBUTE);
        if (!(attr instanceof java.util.Map<?, ?> vars)) {
            return null;
        }
        for (String name : names) {
            Object raw = vars.get(name);
            if (raw == null) {
                continue;
            }
            try {
                return Integer.valueOf(String.valueOf(raw));
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }
}
EOF
```

- [ ] **Step 6: 권한 거부 핸들러 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/config/RestAccessDeniedHandler.java <<'EOF'
package com.example.bitcomputer.config;

import com.example.bitcomputer.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * 권한 거부를 403 으로 응답하면서 감사 로그에 남긴다.
 * 접근 "시도" 자체가 감사 대상이다.
 */
@Component
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private final AuditService auditService;

    public RestAccessDeniedHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException {
        auditService.record(
                "ACCESS_DENIED",
                null,
                null,
                auditService.clientIp(request),
                AuditService.DENIED,
                request.getMethod() + " " + request.getRequestURI());

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
    }
}
EOF
```

- [ ] **Step 7: 조회 컨트롤러 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/controller/AuditLogController.java <<'EOF'
package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 감사 로그 조회. SecurityConfig 에서 SUPER_USER 전용으로 묶여 있다. */
@RestController
@RequestMapping("/api/audit")
public class AuditLogController {

    private final AccessAuditLogRepository repository;

    public AuditLogController(AccessAuditLogRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/logs")
    public ResponseEntity<Page<AccessAuditLog>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size) {
        return ResponseEntity.ok(
                repository.findAllByOrderByOccurredAtDesc(PageRequest.of(page, Math.min(size, 200))));
    }
}
EOF
```

- [ ] **Step 8: 인터셉터와 핸들러 등록**

`apps/api/src/main/java/com/example/bitcomputer/config/WebMvcConfig.java`에 인터셉터를 등록한다.

```java
    private final AuditInterceptor auditInterceptor;

    public WebMvcConfig(AuditInterceptor auditInterceptor) {
        this.auditInterceptor = auditInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(auditInterceptor).addPathPatterns("/api/**");
    }
```

`SecurityConfig`에 거부 핸들러를 연결한다. 생성자에 `RestAccessDeniedHandler`를 주입하고 `exceptionHandling`을 수정한다.

```java
            .exceptionHandling(e -> e
                .authenticationEntryPoint(
                        new HttpStatusEntryPoint(org.springframework.http.HttpStatus.UNAUTHORIZED))
                .accessDeniedHandler(restAccessDeniedHandler)
            )
```

- [ ] **Step 9: 감사 대상 엔드포인트에 애너테이션 부착**

`apps/api/src/main/java/com/example/bitcomputer/controller/PatientController.java`의 단건 조회 메서드에 붙인다.

```java
    @AuditPatientAccess(action = "PATIENT_VIEW")
    @GetMapping("/{id}")
    public ResponseEntity<PatientDTO> getPatient(@PathVariable int id) {
```

같은 방식으로 아래 메서드에도 붙인다. 정확한 메서드명은 각 컨트롤러에서 확인한다.

| 컨트롤러 | 메서드 | action |
|---|---|---|
| `PatientController` | 단건 조회 | `PATIENT_VIEW` |
| `PatientController` | 생성 | `PATIENT_CREATE` |
| `PatientController` | 수정 | `PATIENT_UPDATE` |
| `HistoryController` | 단건 조회 | `HISTORY_VIEW` |
| `HistoryController` | 생성 | `HISTORY_CREATE` |
| `HistoryDiagnoseController` | 생성 | `PRESCRIPTION_CREATE` |
| `AgentController` | `recommendPrescription` | `AI_PRESCRIPTION_RECOMMEND` |
| `AgentDocumentController` | 진단서 생성 | `CERTIFICATE_GENERATE` |

- [ ] **Step 10: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*AuditLogTest*'; cd ../..
```

Expected: PASS 4개

- [ ] **Step 11: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/annotation/ \
        apps/api/src/main/java/com/example/bitcomputer/entity/AccessAuditLog.java \
        apps/api/src/main/java/com/example/bitcomputer/Repository/AccessAuditLogRepository.java \
        apps/api/src/main/java/com/example/bitcomputer/service/AuditService.java \
        apps/api/src/main/java/com/example/bitcomputer/config/AuditInterceptor.java \
        apps/api/src/main/java/com/example/bitcomputer/config/RestAccessDeniedHandler.java \
        apps/api/src/main/java/com/example/bitcomputer/config/WebMvcConfig.java \
        apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java \
        apps/api/src/main/java/com/example/bitcomputer/controller/ \
        apps/api/src/test/java/com/example/bitcomputer/config/AuditLogTest.java
git commit -m "feat: 환자 기록 접근 감사 로그 추가" -m "@AuditPatientAccess 를 붙인 엔드포인트의 접근을 기록한다. 권한 거부도
DENIED 로 남긴다 — 접근 시도 자체가 감사 대상이다.
조회는 SUPER_USER 전용이며 수정·삭제 API 는 두지 않는다."
```

---

## Task 12: 프론트 쿠키 인증 전환

**Files:**
- Modify: `apps/web/src/lib/auth/token.ts`
- Modify: `apps/web/src/services/http/interceptors.ts`
- Modify: `apps/web/src/services/auth.ts`
- Modify: `apps/web/src/components/WaitingStatus.tsx:313,341`
- Modify: `apps/web/src/middleware.ts`

**Interfaces:**
- Consumes: Task 8의 `Set-Cookie: access_token`, Task 10의 `XSRF-TOKEN`
- Produces: 프론트가 토큰 값을 저장하거나 읽지 않는다. `clearTokens()`만 남고 `getAccessToken()`은 제거된다.

- [ ] **Step 1: `token.ts`에서 토큰 저장 제거**

access token은 이제 HttpOnly 쿠키에만 있으므로 JS가 읽을 수 없고, 읽을 필요도 없다.

```bash
cat > apps/web/src/lib/auth/token.ts <<'EOF'
/**
 * 인증 토큰은 서버가 HttpOnly 쿠키로 관리한다.
 *
 * JS 에서 토큰 값을 읽거나 저장하지 않는다 — XSS 로 탈취되는 경로를 막기
 * 위해서다. 로그인 여부 판정은 서버 응답(401)으로 한다.
 */

/** 서버 로그아웃 후 클라이언트 상태를 비운다. 쿠키 삭제는 서버가 한다. */
export function clearClientAuthState(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem("access_token");
    window.localStorage.removeItem("refresh_token");
  } catch {
    // storage 접근 실패는 무시한다
  }
}
EOF
```

- [ ] **Step 2: 인터셉터에서 Authorization 헤더 주입 제거**

```bash
cat > apps/web/src/services/http/interceptors.ts <<'EOF'
import type { AxiosInstance, AxiosError } from "axios";
import { HttpError } from "./types";

/**
 * 인증은 HttpOnly 쿠키(withCredentials)로 전달되므로 Authorization 헤더를
 * 붙이지 않는다. CSRF 토큰은 axios 의 xsrfCookieName/xsrfHeaderName 설정이
 * 자동으로 처리한다.
 */
export function attachInterceptors(instance: AxiosInstance): void {
  instance.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      const status = error.response?.status ?? 0;
      const data = error.response?.data as unknown;
      const body = typeof data === "object" && data !== null ? (data as Record<string, unknown>) : null;
      const detail = body?.detail;
      const detailStr =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((x) =>
                  typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x)
                )
                .join("; ")
            : "";
      const message =
        detailStr ||
        (body?.message != null ? String(body.message) : "") ||
        error.message ||
        "HTTP Error";

      if (status === 401 && typeof window !== "undefined") {
        window.location.href = "/login";
      }

      throw new HttpError(message, status, data);
    }
  );
}
EOF
```

- [ ] **Step 3: `client.ts`에서 토큰 getter 제거**

`apps/web/src/services/http/client.ts`에서 `setAuthTokenGetter`와 `sharedTokenGetter`를 지우고 `attachInterceptors` 호출을 단일 인자로 바꾼다.

```ts
import axios, { type AxiosInstance, type AxiosRequestConfig } from "axios";
import { attachInterceptors } from "./interceptors";
import type { HttpClientOptions } from "./types";

let sharedInstance: AxiosInstance | null = null;
let interceptorsAttached = false;

function createInstance(options?: HttpClientOptions): AxiosInstance {
  const defaultBaseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL && process.env.NEXT_PUBLIC_API_BASE_URL.trim().length > 0
      ? process.env.NEXT_PUBLIC_API_BASE_URL
      : "http://localhost:8080";

  const baseURL = options?.baseURL ?? defaultBaseUrl;
  const timeout = options?.timeoutMs ?? 15000;

  const instance = axios.create({
    baseURL,
    timeout,
    withCredentials: true,
    xsrfCookieName: "XSRF-TOKEN",
    xsrfHeaderName: "X-XSRF-TOKEN",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
  });

  if (!interceptorsAttached) {
    attachInterceptors(instance);
    interceptorsAttached = true;
  }
  return instance;
}
```

`TokenGetter` 타입이 `types.ts`에 남아 있으면 지운다. `setAuthTokenGetter` 호출부를 찾아 제거한다.

```bash
grep -rn "setAuthTokenGetter\|getAccessToken\|setAccessToken\|setRefreshToken\|clearTokens" apps/web/src
```

- [ ] **Step 4: `WaitingStatus.tsx`의 수동 헤더 제거**

313행과 341행 근처에서 토큰을 직접 붙이는 코드를 지운다.

```bash
grep -n "Authorization" apps/web/src/components/WaitingStatus.tsx
```

해당 두 줄과 그 위의 `const token = ...` 줄을 제거한다. 이 컴포넌트가 공용 `http()` 클라이언트를 쓰지 않고 `fetch`를 직접 쓴다면 `credentials: "include"`를 추가한다.

```ts
const res = await fetch(url, {
  method: "GET",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
});
```

- [ ] **Step 5: `middleware.ts`에 주석 명시**

동작은 그대로 두되, 이것이 방어 계층이 아니라는 점을 코드에 남긴다.

```ts
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

/**
 * 낙관적 리다이렉트.
 *
 * 쿠키 "존재"만 확인하며 서명을 검증하지 않는다. 이것은 UX 장치이지 방어
 * 계층이 아니다 — 임의의 쿠키를 심으면 통과한다. 실제 권한 판정은 서버
 * (SecurityConfig)에서만 이뤄지며, 권한 없는 요청은 401/403 으로 막힌다.
 */
export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token")?.value;
  const url = request.nextUrl;

  if (url.pathname === "/") {
    return NextResponse.redirect(new URL(token ? "/dashboard" : "/login", url));
  }

  if (url.pathname.startsWith("/dashboard") && !token) {
    return NextResponse.redirect(new URL("/login", url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/", "/dashboard/:path*"],
};
```

- [ ] **Step 6: 로그인 흐름 수정**

`apps/web/src/services/auth.ts`에서 응답의 `accessToken`을 저장하던 코드를 제거한다. 서버가 쿠키를 내려주므로 로그인 성공 여부만 확인하면 된다.

```bash
grep -n "accessToken\|setAccessToken\|localStorage" apps/web/src/services/auth.ts
```

저장 호출을 지우고 로그인 함수는 성공 시 `/dashboard`로 이동하도록 둔다.

- [ ] **Step 7: 타입 체크와 빌드**

```bash
cd apps/web && yarn install --immutable && yarn tsc --noEmit && yarn build; cd ../..
```

Expected: 타입 오류 없음, 빌드 성공. `getAccessToken` 참조가 남아 있으면 여기서 잡힌다.

- [ ] **Step 8: 커밋**

```bash
git add apps/web/src/lib/auth/token.ts apps/web/src/services/http/ \
        apps/web/src/services/auth.ts apps/web/src/components/WaitingStatus.tsx \
        apps/web/src/middleware.ts
git commit -m "refactor: 프론트를 HttpOnly 쿠키 인증으로 전환" -m "localStorage 토큰 저장과 Authorization 헤더 수동 주입을 제거했다.
middleware 가 방어 계층이 아니라 UX 장치임을 코드에 명시했다."
```

---

## Task 13: 테스트 러너 골격과 smoke test

**Files:**
- Create: `services/xray-rag/tests/test_smoke.py`, `services/prescription/tests/test_smoke.py`, `services/validation-agent/tests/test_smoke.py`, `services/radiology-legacy/tests/test_smoke.py`
- Create: `services/*/pytest.ini` (없는 곳)
- Create: `apps/web/vitest.config.ts`, `apps/web/src/components/__tests__/AIReport.test.tsx`
- Modify: `apps/web/package.json`
- Modify: `services/xray-rag/pytest.ini`

**Interfaces:**
- Consumes: Task 3의 `require_env`, Task 5의 `engineStatus`
- Produces: 각 서비스에서 `python -m pytest` / `yarn test`가 green으로 끝난다.

- [ ] **Step 1: xray-rag smoke test**

기존 `pytest.ini`가 없는 `tests` 디렉터리를 가리키고 있었다. 이제 실제로 만든다.

```bash
cat > services/xray-rag/tests/test_smoke.py <<'EOF'
"""서비스가 뜨고 헬스 응답이 계약대로인지 확인한다."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body_is_json_object():
    body = client.get("/health").json()
    assert isinstance(body, dict)


def test_openapi_exposes_infer_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/infer" in schema["paths"]


def test_infer_response_schema_declares_engine_status():
    schema = client.get("/openapi.json").json()
    properties = schema["components"]["schemas"]["InferenceResponse"]["properties"]
    assert "engineStatus" in properties
EOF
```

- [ ] **Step 2: prescription smoke test**

```bash
cat > services/prescription/tests/test_smoke.py <<'EOF'
from fastapi.testclient import TestClient

from prescription_api import app

client = TestClient(app)


def test_health_returns_200():
    assert client.get("/health").status_code == 200


def test_openapi_exposes_recommend_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/api/agent/prescription/recommend" in schema["paths"]


def test_recommend_response_schema_declares_engine_status():
    schema = client.get("/openapi.json").json()
    properties = schema["components"]["schemas"]["PrescriptionRecommendResponse"]["properties"]
    assert "engineStatus" in properties
EOF

cat > services/prescription/pytest.ini <<'EOF'
[pytest]
testpaths = tests
addopts = -ra
python_files = test_*.py
pythonpath = .
EOF
```

- [ ] **Step 3: validation-agent smoke test**

```bash
mkdir -p services/validation-agent/tests
cat > services/validation-agent/tests/test_smoke.py <<'EOF'
from fastapi.testclient import TestClient

from app.main import app
from app.llm_provider import resolve_provider, stub_tool_decision

client = TestClient(app)


def test_health_returns_200():
    assert client.get("/health").status_code == 200


def test_openapi_exposes_run_endpoint():
    schema = client.get("/openapi.json").json()
    assert "/api/agent/validation/run" in schema["paths"]


def test_stub_provider_selected_by_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert resolve_provider() == "stub"


def test_stub_decision_terminates_with_finalize():
    assert stub_tool_decision(99)["action"] == "FINALIZE"
EOF

cat > services/validation-agent/pytest.ini <<'EOF'
[pytest]
testpaths = tests
addopts = -ra
python_files = test_*.py
pythonpath = .
EOF
```

- [ ] **Step 4: radiology-legacy smoke test**

Flask 앱이므로 `test_client()`를 쓴다.

```bash
mkdir -p services/radiology-legacy/tests
cat > services/radiology-legacy/tests/test_smoke.py <<'EOF'
import pytest

from app import app as flask_app


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def test_is_running_returns_200(client):
    assert client.get("/api/ai/is_running").status_code == 200
EOF

cat > services/radiology-legacy/pytest.ini <<'EOF'
[pytest]
testpaths = tests
addopts = -ra
python_files = test_*.py
pythonpath = .
EOF
```

- [ ] **Step 5: Python 테스트 실행**

```bash
for s in xray-rag prescription validation-agent radiology-legacy; do
  echo "=== $s ==="
  (cd services/$s && LLM_PROVIDER=stub python -m pytest -q)
done
```

Expected: 네 서비스 모두 통과. `ModuleNotFoundError: fastapi` 등이 나오면 해당 서비스의 `requirements.txt`를 설치한다.

`pytest`와 `httpx`가 requirements에 없으면 각 `requirements.txt`에 추가한다.

```
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 6: 프론트 테스트 러너 설치**

```bash
cd apps/web
yarn add -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom
cd ../..
```

- [ ] **Step 7: vitest 설정과 테스트 작성**

```bash
cat > apps/web/vitest.config.ts <<'EOF'
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
EOF

mkdir -p apps/web/src/components/__tests__
cat > apps/web/src/components/__tests__/AIReport.test.tsx <<'EOF'
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AIReport from "../AIReport";

describe("AIReport engineStatus 배지", () => {
  it("mock 엔진이면 경고를 표시한다", () => {
    render(<AIReport engineStatus="mock" />);
    expect(screen.getByRole("status")).toHaveTextContent("mock");
  });

  it("stub 엔진이면 경고를 표시한다", () => {
    render(<AIReport engineStatus="stub" />);
    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("real 엔진이면 경고를 표시하지 않는다", () => {
    render(<AIReport engineStatus="real" />);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
EOF
```

`AIReport`가 필수 props를 더 요구하면 테스트에서 최소값을 채운다. 컴포넌트 시그니처를 확인한다.

```bash
grep -n "export default function AIReport\|interface.*Props" apps/web/src/components/AIReport.tsx
```

- [ ] **Step 8: `package.json`에 test 스크립트 추가**

```json
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint",
    "test": "vitest run"
  },
```

- [ ] **Step 9: 프론트 테스트 실행**

```bash
cd apps/web && yarn test; cd ../..
```

Expected: 3개 통과

- [ ] **Step 10: Spring 테스트 전체 실행**

```bash
cd apps/api && ./gradlew test; cd ../..
```

Expected: BUILD SUCCESSFUL. 기존 14개 테스트 중 인증 활성화로 깨진 것이 있으면 쿠키를 추가해 고친다.

```java
// 기존 컨트롤러 테스트에 인증 쿠키를 붙인다
.cookie(new jakarta.servlet.http.Cookie(
        CookieFactory.ACCESS_TOKEN_COOKIE,
        jwtTokenProvider.generateAccessToken("tester", Role.DOCTOR)))
```

- [ ] **Step 11: 커밋**

```bash
git add services/*/tests/ services/*/pytest.ini services/*/requirements.txt \
        apps/web/vitest.config.ts apps/web/package.json apps/web/src/components/__tests__/ \
        apps/api/src/test/
git commit -m "test: 서비스별 테스트 러너와 smoke test 추가" -m "Python 4개 서비스에 pytest, 프론트에 vitest 를 설치하고 각각 헬스·스키마
smoke 를 넣어 green 기준선을 만든다. xray-rag 의 pytest.ini 가 가리키던
tests 디렉터리를 실제로 생성했다."
```

---

## Task 14: CI 파이프라인과 gitleaks

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.gitleaks.toml`

**Interfaces:**
- Consumes: Task 13의 테스트 러너
- Produces: push·PR마다 lint/build/test + gitleaks가 돈다.

- [ ] **Step 1: gitleaks 설정**

```bash
cat > .gitleaks.toml <<'EOF'
title = "BitComputer gitleaks config"

[extend]
useDefault = true

[allowlist]
description = "예시 파일과 테스트 픽스처는 검사에서 제외한다"
paths = [
  '''infra/\.env\.example''',
  '''apps/api/src/test/resources/application-test\.properties''',
]
EOF
```

테스트용 JWT secret이 `application-test.properties`에 있으므로 허용 목록에 넣는다. 실제 값이 아니다.

- [ ] **Step 2: 워크플로 작성**

```bash
mkdir -p .github/workflows
cat > .github/workflows/ci.yml <<'EOF'
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  secrets:
    name: gitleaks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  api:
    name: apps/api
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '23'
      - uses: gradle/actions/setup-gradle@v4
      - name: test
        working-directory: apps/api
        run: ./gradlew test

  web:
    name: apps/web
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: enable corepack
        run: corepack enable
      - name: install
        working-directory: apps/web
        run: yarn install --immutable
      - name: lint
        working-directory: apps/web
        run: yarn lint
      - name: test
        working-directory: apps/web
        run: yarn test
      - name: build
        working-directory: apps/web
        run: yarn build
        env:
          NEXT_PUBLIC_API_BASE_URL: http://localhost:8080

  services:
    name: services/${{ matrix.service }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        service: [xray-rag, prescription, validation-agent, radiology-legacy]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: install
        working-directory: services/${{ matrix.service }}
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: test
        working-directory: services/${{ matrix.service }}
        env:
          LLM_PROVIDER: stub
          ARANGO_PASSWORD: ci-not-a-real-password
        run: python -m pytest -q

  e2e:
    name: compose e2e
    runs-on: ubuntu-latest
    needs: [api, web, services]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: write .env
        working-directory: infra
        run: |
          cp .env.example .env
          {
            echo "MYSQL_ROOT_PASSWORD=${{ secrets.MYSQL_ROOT_PASSWORD }}"
            echo "MYSQL_PASSWORD=${{ secrets.MYSQL_ROOT_PASSWORD }}"
            echo "ARANGO_PASSWORD=${{ secrets.ARANGO_PASSWORD }}"
            echo "RABBITMQ_PASSWORD=guest"
            echo "RABBITMQ_ERLANG_COOKIE=ci-cookie"
            echo "JWT_SECRET=${{ secrets.JWT_SECRET }}"
            echo "LLM_PROVIDER=stub"
          } >> .env
      - name: up
        working-directory: infra
        run: docker compose --env-file .env up -d --build
      - name: wait for api
        run: |
          for i in $(seq 1 60); do
            if curl -fsS http://localhost:8080/actuator/health >/dev/null; then
              echo "api ready"; exit 0
            fi
            sleep 5
          done
          echo "api did not become ready"; exit 1
      - name: run e2e
        run: |
          pip install pytest httpx
          python -m pytest tests/e2e -q
      - name: dump logs on failure
        if: failure()
        working-directory: infra
        run: docker compose --env-file .env logs --tail 200
EOF
```

- [ ] **Step 3: GitHub Secrets 등록**

값을 대화형으로 입력받는다. `--body`로 명령줄에 넣지 않는다 — 셸 히스토리에 남는다.

```bash
gh secret set JWT_SECRET
gh secret set MYSQL_ROOT_PASSWORD
gh secret set ARANGO_PASSWORD
```

`JWT_SECRET`은 64바이트 이상이어야 한다. 값 생성:

```bash
openssl rand -base64 64
```

등록 확인:

```bash
gh secret list
```

Expected: `ARANGO_PASSWORD`, `JWT_SECRET`, `MYSQL_ROOT_PASSWORD` 세 항목.

- [ ] **Step 4: gitleaks 로컬 검증**

```bash
docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest detect --source=/repo --config=/repo/.gitleaks.toml --no-git -v
```

Expected: `no leaks found`. 유출이 잡히면 해당 파일을 제거하거나 허용 목록에 추가한다.

- [ ] **Step 5: 커밋 및 CI 확인**

```bash
git add .github/workflows/ci.yml .gitleaks.toml
git commit -m "ci: 파이프라인과 시크릿 스캔 추가" -m "workspace 별 lint/build/test 를 병렬로 돌리고 gitleaks 로 시크릿 재유입을
차단한다. e2e 잡은 LLM_PROVIDER=stub 으로 실제 LLM 키 없이 전체 경로를
검증한다."
git push -u origin main
gh run watch
```

Expected: `secrets`, `api`, `web`, `services` 잡이 모두 green. `e2e`는 Task 15 완료 전까지 실패한다 — 다음 태스크에서 만든다.

---

## Task 15: E2E 시나리오

**Files:**
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_core_flow.py`

**Interfaces:**
- Consumes: Task 8의 로그인 쿠키, Task 9의 RBAC, Task 10의 CSRF, Task 11의 감사 로그
- Produces: `python -m pytest tests/e2e`가 실행 중인 compose 스택을 검증한다.

- [ ] **Step 1: 픽스처 작성**

```bash
cat > tests/e2e/conftest.py <<'EOF'
"""E2E 픽스처.

실행 중인 compose 스택을 대상으로 한다. API_BASE_URL 로 대상을 바꿀 수 있다.
"""
from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8080")


def _register(client: httpx.Client, username: str, role: str) -> None:
    """이미 있으면 409 가 오는데 그대로 진행한다."""
    client.post(
        "/api/user/register",
        json={
            "name": username,
            "deptId": 1,
            "role": role,
            "username": username,
            "password": "TestPassw0rd!",
        },
    )


def login_as(role: str) -> httpx.Client:
    """해당 역할로 로그인한 클라이언트를 만든다. 쿠키는 클라이언트가 보관한다."""
    username = f"e2e_{role.lower()}"
    client = httpx.Client(base_url=BASE_URL, timeout=60.0, follow_redirects=False)

    _register(client, username, role)

    response = client.post(
        "/api/user/login",
        json={"username": username, "password": "TestPassw0rd!"},
    )
    assert response.status_code == 200, f"{role} 로그인 실패: {response.text}"
    assert "access_token" in client.cookies, "로그인 응답에 access_token 쿠키가 없다"
    return client


def csrf_headers(client: httpx.Client) -> dict[str, str]:
    """상태 변경 요청에 필요한 CSRF 헤더를 만든다."""
    token = client.cookies.get("XSRF-TOKEN")
    return {"X-XSRF-TOKEN": token} if token else {}


@pytest.fixture()
def doctor() -> httpx.Client:
    client = login_as("DOCTOR")
    yield client
    client.close()


@pytest.fixture()
def receptionist() -> httpx.Client:
    client = login_as("RECEPTIONIST")
    yield client
    client.close()


@pytest.fixture()
def super_user() -> httpx.Client:
    client = login_as("SUPER_USER")
    yield client
    client.close()
EOF
```

- [ ] **Step 2: E2E 시나리오 작성**

```bash
cat > tests/e2e/test_core_flow.py <<'EOF'
"""핵심 경로와 권한 거부를 검증한다.

RBAC 은 '되는 것'보다 '안 되는 것'을 확인해야 의미가 있으므로, 권한 거부와
그 감사 기록까지 포함한다.
"""
from __future__ import annotations

import httpx
import pytest

from conftest import csrf_headers


def test_unauthenticated_patient_access_is_rejected():
    with httpx.Client(base_url="http://localhost:8080", timeout=30.0) as client:
        response = client.get("/api/patients/1")
    assert response.status_code == 401


def test_health_endpoint_is_public():
    with httpx.Client(base_url="http://localhost:8080", timeout=30.0) as client:
        assert client.get("/actuator/health").status_code == 200


@pytest.fixture()
def patient_id(doctor: httpx.Client) -> int:
    response = doctor.post(
        "/api/patients",
        headers=csrf_headers(doctor),
        json={
            "name": "E2E 환자",
            "birth": "1990-01-01",
            "gender": "M",
            "phone": "010-0000-0000",
        },
    )
    assert response.status_code in (200, 201), f"환자 생성 실패: {response.text}"
    body = response.json()
    return int(body.get("id") or body.get("patientId"))


def test_doctor_can_create_and_read_patient(doctor: httpx.Client, patient_id: int):
    response = doctor.get(f"/api/patients/{patient_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "E2E 환자"


def test_doctor_reaches_ai_recommendation(doctor: httpx.Client, patient_id: int):
    """stub provider 이므로 실제 LLM 없이 응답이 온다."""
    response = doctor.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(doctor),
        json={"historyDiagnoseId": 1, "patientId": patient_id},
    )
    # 권한은 통과해야 한다. 데이터가 없어 400/404 가 날 수는 있으나 403 은 안 된다.
    assert response.status_code != 403, "DOCTOR 가 AI 추천에서 거부됐다"


def test_stub_engine_status_is_exposed():
    """처방 서비스가 stub 으로 돌고 있음을 응답에서 확인할 수 있어야 한다."""
    with httpx.Client(base_url="http://localhost:8001", timeout=60.0) as client:
        response = client.post(
            "/api/agent/prescription/recommend",
            json={
                "patient_id": "e2e",
                "symptoms": "기침",
                "history": "",
                "top_rx": [{"처방명": "테스트약", "처방코드": "T001"}],
                "similar_outcomes": "",
                "disease_codes": [],
                "fetch_top_rx_from_arango": False,
                "fetch_cohort_rx_from_arango": False,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engineStatus"] == "stub"
    assert len(body["prescriptions"]) == 3


def test_receptionist_is_denied_ai_recommendation(receptionist: httpx.Client):
    response = receptionist.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(receptionist),
        json={"historyDiagnoseId": 1},
    )
    assert response.status_code == 403


def test_denied_attempt_is_audited(receptionist: httpx.Client, super_user: httpx.Client):
    receptionist.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(receptionist),
        json={"historyDiagnoseId": 1},
    )

    response = super_user.get("/api/audit/logs?page=0&size=50")
    assert response.status_code == 200

    entries = response.json()["content"]
    denied = [
        e for e in entries
        if e["outcome"] == "DENIED" and e["actorUsername"] == "e2e_receptionist"
    ]
    assert denied, "권한 거부가 감사 로그에 기록되지 않았다"
    assert denied[0]["actorRole"] == "RECEPTIONIST"


def test_patient_lookup_is_audited(doctor: httpx.Client, super_user: httpx.Client, patient_id: int):
    doctor.get(f"/api/patients/{patient_id}")

    response = super_user.get("/api/audit/logs?page=0&size=50")
    entries = response.json()["content"]

    views = [
        e for e in entries
        if e["action"] == "PATIENT_VIEW" and e["targetPatientId"] == patient_id
    ]
    assert views, "환자 조회가 감사 로그에 기록되지 않았다"
    assert views[0]["actorRole"] == "DOCTOR"
    assert views[0]["requestIp"]


def test_doctor_cannot_read_audit_log(doctor: httpx.Client):
    assert doctor.get("/api/audit/logs").status_code == 403
EOF
```

- [ ] **Step 3: 로컬에서 실행**

```bash
cd infra && LLM_PROVIDER=stub docker compose --env-file .env up -d --build && cd ..
sleep 60
pip install pytest httpx
python -m pytest tests/e2e -v
```

Expected: 10개 통과.

실패하면 원인별로 대응한다.

| 증상 | 원인 | 대응 |
|---|---|---|
| 로그인 401 | 회원가입이 409로 막히고 비밀번호 불일치 | 해당 사용자 삭제 후 재실행 |
| 환자 생성 403 | CSRF 헤더 누락 | `csrf_headers` 반환값이 비었는지 확인 |
| `engineStatus != "stub"` | compose에 `LLM_PROVIDER` 미전달 | Task 4 Step 8 확인 |
| 감사 로그 비어 있음 | 애너테이션 미부착 | Task 11 Step 9 확인 |

- [ ] **Step 4: CI에서 확인**

```bash
git add tests/e2e/
git commit -m "test: 핵심 경로와 권한 거부 E2E 추가" -m "DOCTOR 로그인부터 AI 추천까지의 경로와, RECEPTIONIST 의 거부 및 그
감사 기록을 검증한다. LLM_PROVIDER=stub 이라 실제 LLM 키가 필요 없다."
git push
gh run watch
```

Expected: `e2e` 잡을 포함해 모든 잡이 green.

---

## 완료 확인

spec 8장의 완료 조건을 순서대로 확인한다.

- [ ] **1. 클론 후 한 번에 기동**

```bash
cd infra && cp .env.example .env
# .env 를 채운 뒤
docker compose --env-file .env up -d --build && docker compose --env-file .env ps
```
Expected: 전 컨테이너 `Up`

- [ ] **2. 가중치 없이 CI green**

```bash
gh run list --limit 1
```
Expected: 최신 run이 `success`

- [ ] **3. 무인증 401**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/patients/1
```
Expected: `401`

- [ ] **4~5. 권한 거부와 감사 로그**

```bash
python -m pytest tests/e2e -v -k "audited or denied"
```
Expected: 통과

- [ ] **6. gitleaks 통과**

```bash
docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest detect --source=/repo --config=/repo/.gitleaks.toml --no-git
```
Expected: `no leaks found`

- [ ] **7. 유출 키 폐기 (수동)**

spec 6.6의 체크리스트를 확인한다. Google AI Studio, OpenAI 콘솔에서 revoke 완료 여부.

- [ ] **8. 기존 저장소 archive**

```bash
for r in AI_BackEnd Back-End Front-End GraphDB ValidationAgent XrayGraphRAG; do
  gh repo edit PatboongIsBetterthanSyuboong/$r --visibility private 2>/dev/null
  gh api -X PATCH repos/PatboongIsBetterthanSyuboong/$r -f archived=true
done
```
Expected: 각 저장소가 archived 상태

- [ ] **9. engineStatus 노출**

```bash
curl -s http://localhost:8000/openapi.json | grep -o engineStatus | head -1
```
Expected: `engineStatus`

- [ ] **10. stub E2E 통과**

```bash
python -m pytest tests/e2e -q
```
Expected: 전체 통과
