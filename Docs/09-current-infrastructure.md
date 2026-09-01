# 현재 인프라 구조

AWS 배포와 GCP DR 설계의 출발점이 되는 **지금 상태** 를 적는다. 앞으로 무엇을
어디로 옮길지 판단하려면 지금 무엇이 무엇에 의존하는지가 먼저 분명해야 한다.

이 문서는 계획이 아니라 **관측**이다. 모든 수치는 2026-09-01 로컬 스택에서 잰
값이고, 추정한 곳은 그렇게 표시했다.

---

## 1. 서비스 12개

`infra/docker-compose.yml` 이 띄우는 전부다.

### 애플리케이션 8개 (소스에서 빌드)

| 서비스 | 포트 | 이미지 | 역할 | 빌드 컨텍스트 |
|---|---|---|---|---|
| `frontend` | 3000 | 1.72GB | Next.js 화면 | `apps/web` |
| `spring-boot` | 8080 | 608MB | 업무 API·인증·job 발행 | `apps/api` |
| `prescription-api` | 8001 | 565MB | 처방 추천(그래프 조회 + LLM) | `services/prescription` |
| `certificate-api` | 5001 | 565MB | 진단서 생성 | `services/prescription` |
| `validation-agent` | 8002 | 359MB | 검증 에이전트(RabbitMQ 소비) | `services/validation-agent` |
| `llm-gateway` | 8003 | 259MB | **유일하게 LLM 키를 쥔 곳** | `services/llm-gateway` |
| `xraygraph` | 8000 | 2.30GB | X-ray 유사사례 검색 | `services/xray-rag` |
| `flask-radiology` | 5000 | 3.18GB | 구 X-ray 단일추론(대체 엔진) | `services/radiology-legacy` |

`prescription-api` 와 `certificate-api` 는 **같은 빌드 컨텍스트**를 쓴다. 하나를
고치면 둘 다 다시 빌드해야 한다.

### 인프라 4개 (이미지 수령)

| 서비스 | 포트 | 이미지 | AWS 대응 |
|---|---|---|---|
| `mysql` | 3306 | mysql:8, 1.12GB | RDS |
| `redis` | 6379 | redis:7-alpine, 57.8MB | ElastiCache |
| `rabbitmq` | 5672 | rabbitmq:3-management, 392MB | AmazonMQ 또는 인클러스터 |
| `arangodb` | 8529 | arangodb:3.12, 883MB | **관리형 등가물 없음 — 인클러스터 필수** |

`arango-init` 은 기동 시 한 번 돌고 종료하는 초기화 컨테이너다.

---

## 2. 데이터 저장소 세 갈래

### 2.1 MySQL — 업무 데이터

| 테이블 | 행 수 | 출처 | 갱신 |
|---|---:|---|---|
| `disease` | 50,941 | `apps/api/상병코드.xlsx` | 엑셀 갱신 시 |
| `diagnose` | 505,954 | `apps/api/처방코드.xlsx` | 엑셀 갱신 시 |
| `patient` / `employee` / 진료 이력 | 운영 중 생성 | 화면 | 상시 |

적재는 `apps/api/scripts/import_master_codes.py` 가 엑셀 → CSV → `LOAD DATA` 로
넣는다.

### 2.2 ArangoDB — 그래프 두 벌

**`bitcomputer_graph`** (처방 추천)

```
visits 1190   diagnoses 19   order_lines 7001   prescription_masters 880
special_notes 1025   간선 5종
```

출처는 `packages/graph-etl/20260406_상병별 처방코드 추출_특이사항 추가.xlsx` 이고,
`graph_normalize.py` → `output/` CSV 14개 → `import_to_arango.py` 로 들어간다.

여기에 **합성 케이스 120건**(상병 10종 × 방문 12)이 `output_synthetic/` 에서
`--append` 로 얹힌다. 원본 엑셀에 상병이 9종뿐이라 감기·위염 같은 일상 상병에
추천이 나오지 않던 것을 메운 것이다. 합성분은 `source="synthetic"` 과
`VISIT_SYN...` 키로 **언제든 가려낼 수 있다.**

> **ETL 직후 컬렉션은 14개, 앱을 한 번이라도 쓰면 17개다.** 처방 추천 피드백
> 고리가 `recommendation_histories`·`recommendation_prescriptions`·
> `history_recommended_prescription` 을 실행 중에 만든다. 개수로 적재 성공을
> 판단하면 안 된다.

**`xray_graph_db`** (X-ray 유사사례)

```
xray_cases 202   diseases 12   findings 10   rois 10   간선 3종
벡터 인덱스 4개 (dim=1024, cosine)
roiMaskVersion   cv_lung_heart_v1
embeddingVersion densenet121_imagenet_1024
```

CheXpert `valid` split(frontal 202장)을 `scripts/seed_chexpert.py` 로 적재한다.
케이스 키를 원본 경로에서 유도하므로 **재실행이 덮어쓰기**다.

### 2.3 Redis

세션·캐시. 시딩 대상 아님.

---

## 3. 볼륨 6개 — AWS 이전 시 갈라지는 지점

```
mysql-data       /var/lib/mysql                          RDS 로 대체
arango-data      /var/lib/arangodb3                      인클러스터 + EBS
arango-apps      /var/lib/arangodb3-apps                 인클러스터 + EBS
rabbitmq-data    /var/lib/rabbitmq                       AmazonMQ 또는 EBS
images-startup   (아래 참조)
xray-storage     /app/storage                            S3 권장
```

### 3.1 `images-storage` — EBS 로 안 되는 볼륨

**두 서비스가 공유한다.**

```
spring-boot      /app/BitComputer/images            (compose 339행)
flask-radiology  /app/Back-End/BitComputer/images   (compose 102행)
```

Spring 이 업로드 영상을 저장하고 flask 가 읽는다. **ReadWriteMany 가 필요한데
EBS 는 ReadWriteOnce 다.** EFS 로 가거나 S3 로 옮겨야 한다.

`xraygraph` 는 이 볼륨을 쓰지 않는다 — Spring 이 파일을 읽어 multipart 로
POST 한다. 그래서 xraygraph 만 놓고 보면 공유 스토리지가 필요 없다.

### 3.2 볼륨이 아닌 바인드 마운트 하나

```yaml
xraygraph:
  volumes:
    - ../services/radiology-legacy:/app/weights:ro
  environment:
    SQUID_MODEL_DIR: /app/weights/squid_exp1_256_mask
```

**SQUID 이상탐지 가중치**(`model.pth`)를 `radiology-legacy` 디렉터리에서 읽는다.
이게 없으면 `engineStatus` 가 `real` 에서 `mock` 으로 떨어진다.

K8s 에는 이런 바인드 마운트가 없으므로 **이미지에 굽거나 S3 + initContainer** 로
넣어야 한다. `flask-radiology` 이미지를 안 띄우더라도 **이 디렉터리는 지울 수
없다.**

### 3.3 갱신이 필요한 것은 셋

| 볼륨 | 갱신 필요 | 방식 |
|---|---|---|
| `mysql-data` | O | 엑셀 → `import_master_codes.py` |
| `arango-data` | O | 엑셀 → ETL → `import_to_arango.py` (+ 합성 `--append`) |
| `xray-storage` | O | CheXpert 시드 (모델·마스크 바꾸면 전량 재적재) |
| `images-storage` | X | 운영 중 업로드만 |
| `rabbitmq-data` | X | — |
| `arango-apps` | X | — |

---

## 4. 서비스 간 의존

```
브라우저 -> frontend(3000) -> spring-boot(8080)
                                 |
                                 +-- prescription-api(8001) --+
                                 +-- certificate-api(5001) ---+-- llm-gateway(8003) -> 상류 LLM
                                 +-- xraygraph(8000)          |
                                 +-- RabbitMQ -> validation-agent(8002) --+
                                 |                                 |
                                 +-- MySQL / Redis                 +-- prescription-api 재호출
                                                                   +-- ArangoDB
```

**LLM 자격증명은 `llm-gateway` 하나만 갖는다.** 호출 서비스는 게이트웨이 URL 만
안다. 시크릿 관리 범위가 그만큼 좁다.

**`validation-agent` 는 현재 모델을 호출하지 않는다.** 판정이 전부 결정론적
규칙에서 나오며 `llmStatus` 가 `rule` 이다. 그래서 게이트웨이 의존이 사실상
없다.

---

## 5. 환경변수 — AWS 로 옮길 때 갈라지는 축

`infra/.env` 37개 키. 성격별로 보관 위치가 달라진다.

| 성격 | 예 | 권장 보관 |
|---|---|---|
| 자격증명 | `LLM_API_KEY`, `MYSQL_ROOT_PASSWORD`, `ARANGO_PASSWORD`, `JWT_SECRET`, `RABBITMQ_ERLANG_COOKIE` | Secrets Manager |
| 접속 정보 | `*_BASE_URL`, `ARANGO_HOST` | Parameter Store (테라폼 출력) |
| 동작 토글 | `USE_PSPNET_ROI`, `USE_TORCH_*`, `LLM_PROVIDER`, `RADIOLOGY_ENGINE` | ConfigMap |
| 빌드 시점 | **없다** | 프론트 빌드 인자를 전부 없앴다 (§11) |

### 5.1 토글 하나가 코드와 compose 양쪽에 기본값을 갖는다

`USE_PSPNET_ROI` 는 `app/config.py` 와 `docker-compose.yml` 둘 다 기본값을 갖는데,
**적재 스크립트는 호스트에서 돌아 compose 를 거치지 않는다.** 두 값이 어긋나면
저장 코퍼스와 질의가 서로 다른 해부 기준 위에 놓이고 **양쪽 다 정상으로 보인다.**

실제로 그 상태가 한 번 만들어졌고, `test_toggle_defaults_match_compose.py` 가
지금 그것을 막는다. **K8s 로 옮길 때 ConfigMap 과 코드 기본값 사이에 같은 함정이
다시 생긴다** — 적재 Job 과 런타임 파드가 같은 ConfigMap 을 보게 해야 한다.

---

## 6. 이미지 크기와 그 원인

```
flask-radiology  3.18GB      torch 2.11.0+cpu + PyG 확장
xraygraph        2.30GB      torch 2.13.0+cpu + torchxrayvision
frontend         1.72GB
나머지 5개        259MB~608MB
전체              14.4GB
```

전에는 두 torch 이미지가 **17.8GB** 였다. PyPI 기본 `torch` 가 CUDA 빌드라
nvidia 런타임(2.7GB)을 끌고 왔기 때문이다. GPU 를 쓰지 않으므로 CPU 전용
인덱스로 고정해 13GB 를 줄였고, 부수 효과로 **X-ray 추론이 10~15초에서 3~4초**가
됐다.

```
services/xray-rag/requirements.txt
services/radiology-legacy/requirements.txt
  --index-url https://download.pytorch.org/whl/cpu
  --extra-index-url https://pypi.org/simple
```

GPU 노드로 옮기는 날에는 이 두 줄을 지우면 되고, 그때 용량을 다시 치른다.

---

## 7. 성능 실측 (CPU 14코어)

| 경로 | 소요 |
|---|---|
| X-ray 추론 (2회차 이후) | 3~4초 |
| X-ray 추론 (첫 회, 모델 로드 포함) | 최대 26초 |
| 처방 추천 | 7~9초 |
| 검증 에이전트 전 구간 | 12~14초 |
| CheXpert 적재 202건 (`USE_PSPNET_ROI=false`) | 약 4.5분 |
| CheXpert 적재 202건 (`true`) | 약 15분 |

**웹 타임아웃이 60초다**(`RADIOLOGY_ANALYZE_TIMEOUT_MS`). 전에는 axios 기본값
15초를 쓰고 있어 추론 시간과 경계에 걸렸다 — 서버는 정상 처리 중인데 브라우저만
포기하는 상태였다. Java `RestTemplate` 은 180초다.

노드 사이징의 하한이 여기서 나온다. **X-ray 파드는 CPU 를 다 쓰고 메모리
1.4GB 를 잡는다.**

---

## 8. CI 와 테스트

GitHub Actions 9잡.

```
apps/api  apps/web  gitleaks
services/{prescription, validation-agent, llm-gateway, xray-rag, radiology-legacy}
compose e2e
```

`compose e2e` 는 **전체를 빌드하지 않는다.** 러너 디스크가 14GB 라
`mysql redis rabbitmq arangodb arango-init prescription-api spring-boot` 만 띄우고
로그인 → 환자 → 상병 → AI 처방 추천 경로를 검증한다. `LLM_PROVIDER=stub` 으로
돈다.

**이 `stub` 이 GCP DR 의 seam 이다** — 이미 CI 가 그 형상으로 매번 돌고 있다.

---

## 9. GCP DR 로 가져갈 범위

AI 관련 API 를 **전부 배제**하고 EMR 코어만 가져간다.

### 가져가는 것

```
frontend        Next.js 화면
spring-boot     업무 API·인증
Cloud SQL       disease / diagnose 마스터 + 환자·진료 이력
```

### 두고 가는 것

```
prescription-api   certificate-api   validation-agent   llm-gateway
xraygraph          flask-radiology   ArangoDB           RabbitMQ
```

ArangoDB 와 RabbitMQ 가 함께 빠진다 — 전자는 처방 추천 그래프 전용이고 후자는
검증 job 전용이라 AI 를 걷어내면 소비자가 없다. **결과적으로 DR 쪽 상태 저장소는
Cloud SQL 하나**가 되어 동기화 대상이 단순해진다.

### 별도 이미지를 만들지 않는다

`LLM_PROVIDER=stub` 과 `RADIOLOGY_ENGINE` 이라는 seam 이 이미 있고 CI 가 그것을
매번 검증한다. 이미지를 갈래로 나누면 빌드·테스트 표면이 두 배가 되고 두 갈래가
조용히 어긋난다. **같은 이미지, 다른 배포 프로파일** 로 간다.

### 먼저 검증해야 할 것

**Spring 이 AI 서비스 없이 정상 동작하는지 확인된 바 없다.** 화면이 깨지는지,
빈 상태로 뜨는지, 예외를 던지는지 재 봐야 한다. 로컬에서 그 서비스들만 내리고
바로 시험할 수 있다 — **DR 설계를 확정하기 전에 이걸 먼저 재는 것이 순서다.**

---

## 10. 동기화 대상

DR 이 Cloud SQL 하나로 좁혀졌으므로 선택지가 단순하다.

**1단계 — VPN 없이**

```
RDS --mysqldump--> S3 --Storage Transfer--> GCS --import--> Cloud SQL
```

RPO 가 시간 단위여도 되면 이걸로 충분하고, 사설망 연결을 만들 필요가 없다.

**2단계 — RPO 를 분 단위로 줄여야 할 때**

GCP Database Migration Service 로 RDS 를 외부 소스로 두고 연속 CDC 를 건다.
`AWS Site-to-Site VPN ↔ GCP HA VPN`(BGP)과 RDS 쪽 `binlog_format=ROW`,
binlog 보존 시간 설정이 필요하다.

**마스터 코드는 동기화 대상이 아니다.** `disease`·`diagnose` 는 엑셀에서
재생성되는 파생 데이터라 GCP 쪽에서 같은 스크립트를 돌리면 된다. 동기화가
필요한 것은 **환자·진료 이력** 뿐이다.

---

## 11. 알려진 제약

**`arangodb` 는 AWS 관리형 등가물이 없다.** 인클러스터 + EBS 로 운영해야 하고,
EBS 가 AZ 에 묶이므로 노드 장애 시 같은 AZ 로 재스케줄되어야 한다.

**프론트 이미지는 환경 의존이 없다.** 예전에는 `NEXT_PUBLIC_API_BASE_URL` 과
`NEXT_PUBLIC_AI_FEATURES_ENABLED` 두 빌드 인자가 있었고, `NEXT_PUBLIC_` 값은 번들에
박히므로 도메인마다 하나 DR 용으로 또 하나씩 이미지가 갈렸다. 둘 다 없앴다 —
API 는 상대 경로로, AI 유무는 서버가 내는 503 문구로 대체했다.

**대신 조건이 하나 붙는다. 프론트와 API 가 같은 호스트명 아래 있어야 한다.**
AWS 는 CloudFront 가 `/*` 와 `/api/*` 를 갈라 그 조건을 만든다. **GCP DR 도 같은
구조여야 하고, 아니면 프론트 이미지가 다시 갈라진다.**

**진단서 평가 경로(`/api/agent/document/evaluate`)는 죽어 있다.**
`CertificateEvaluationServiceImpl` 이 게이트웨이를 거치지 않고 Gemini 를 직접
호출하는데 키가 폐기됐다. 그 화면은 어디서도 링크되지 않는다. **게이트웨이를
우회하는 유일한 LLM 경로**이므로 시크릿 정리 시 함께 정리 대상이다.

**합성 데이터가 그래프의 10%다**(방문 120/1190). 프로덕션에 그대로 올릴지는
정해야 한다. `source="synthetic"` 으로 걸러낼 수 있다.

---

## 12. 관련 문서

| 문서 | 내용 |
|---|---|
| [07-runbook-data-loading.md](07-runbook-data-loading.md) | 데이터 적재 절차. 볼륨을 지우고 처음부터 검증한 상태 |
| [08-runbook-container-images.md](08-runbook-container-images.md) | 이미지 빌드·배포, 낡은 이미지 판별 |
| [05-data-and-deployment.md](05-data-and-deployment.md) | 환경변수 전체 표 |
| [01-system-architecture.md](01-system-architecture.md) | 서비스 구성과 데이터 흐름 |
| [04-ai-services-and-agents.md](04-ai-services-and-agents.md) | AI 서비스 내부 구조 |
