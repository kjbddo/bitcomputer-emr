# BitComputer 실행 / 데이터 적재 가이드

이 문서는 전체 Docker 환경 실행, XrayGraphRAG 데이터 적재, 처방 추천용 ArangoDB 적재, 진료 데이터 검증 에이전트, 벡터 인덱싱, 종료 방법을 정리한다.

## 1. 전체 서비스 실행

루트 디렉터리에서 실행한다.

```powershell
cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer"
docker compose --env-file .env.docker up -d --build
```

`--build`는 코드, Dockerfile, requirements, package 의존성이 바뀐 뒤에 필요하다. 단순히 다시 켜는 경우에는 아래처럼 실행해도 된다.

```powershell
docker compose --env-file .env.docker up -d
docker compose --env-file .env.docker up -d frontend
```

실행되는 주요 서비스:

| 서비스 | 컨테이너 | 포트 | 역할 |
|---|---|---:|---|
| Front-End | `bit-frontend` | 3000 | Next.js UI |
| Spring Boot | `bit-spring-boot` | 8080 | WAS / API |
| Flask 영상판독 | `bit-flask-radiology` | 5000 | 기존 영상판독 엔진 |
| 진단서 의사소견 | `bit-certificate-api` | 5001 | LLM 게이트웨이 경유 진단서 문장 생성 |
| 처방 추천 | `bit-prescription-api` | 8001 | ArangoDB + LLM 게이트웨이 경유 처방 추천 |
| 진료 데이터 검증 | `bit-validation-agent` | 8002 | LangGraph 기반 처방 추천/검증 ReAct worker |
| XrayGraphRAG | `bit-xraygraph` | 8000 | X-ray 유사 사례 검색 / 상병 추론 |
| MySQL | `bit-mysql` | 3307 | Spring 업무 DB |
| Redis | `bit-redis` | 6379 | 캐시 |
| RabbitMQ | `bit-rabbitmq` | 5672 / 15672 | 처방 추천/검증 비동기 메시지 큐 / 관리 UI |
| ArangoDB | `bit-arangodb` | 8529 | 처방 그래프 + XrayGraphRAG DB |

상태 확인:

```powershell
docker compose --env-file .env.docker ps
```

헬스 체크:

```powershell
curl http://localhost:8080/actuator/health
curl http://localhost:8000/health
curl http://localhost:5001/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

## 2. 전체 서비스 종료

데이터를 유지하면서 종료:

```powershell
docker compose --env-file .env.docker down
```

다시 켜면 MySQL/ArangoDB 데이터는 유지된다.

데이터까지 모두 삭제:

```powershell
docker compose --env-file .env.docker down -v
docker system prune -a --volumes
```

주의: `-v`를 붙이면 Docker volume이 삭제된다. 그러면 MySQL, ArangoDB 데이터가 모두 사라지므로 Xray 데이터, 처방 그래프, 환자/진료 데이터 등을 다시 채워야 한다.

## 3. MySQL 상병/처방 마스터 데이터 적재

`docker compose down -v`로 볼륨을 삭제했거나 MySQL을 새로 만들었다면 프론트의 상병/진단 DB 조회용 마스터 데이터를 다시 적재해야 한다.

루트 디렉터리에서 실행한다. MySQL 컨테이너(`bit-mysql`)가 실행 중이어야 한다.

```powershell
cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer"
python -m pip install openpyxl
python .\Back-End\scripts\import_master_codes.py
```

기본 동작:

- `Back-End\상병코드.xlsx`를 `Back-End\generated\master-codes\disease_codes.csv`로 변환한 뒤 `disease` 테이블에 적재한다.
- `Back-End\처방코드.xlsx`를 `Back-End\generated\master-codes\prescription_codes.csv`로 변환한 뒤 `diagnose` 테이블에 적재한다.
- 적재 전 `disease`, `diagnose` 테이블을 비우고 auto increment를 1부터 다시 시작한다.

CSV만 생성하고 DB에는 넣지 않으려면:

```powershell
python .\Back-End\scripts\import_master_codes.py --convert-only
```

상병 또는 처방 중 하나만 다시 적재하려면:

```powershell
python .\Back-End\scripts\import_master_codes.py --target disease
python .\Back-End\scripts\import_master_codes.py --target diagnose
```

적재 확인:

```powershell
docker exec bit-mysql mysql -uroot -p<YOUR_MYSQL_ROOT_PASSWORD> -D bitcomputer -e "SELECT COUNT(*) AS disease_count FROM disease; SELECT COUNT(*) AS diagnose_count FROM diagnose;"
curl "http://localhost:8080/api/diseases?page=0&size=5"
curl "http://localhost:8080/api/diagnoses?page=0&size=5"
```

## 4. XrayGraphRAG 데이터 적재

### 4.1. 사전 준비

XrayGraphRAG 스크립트는 로컬 venv에서 실행하는 것을 권장한다. CheXpert archive가 호스트 경로에 있기 때문이다.

```powershell
cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer\XrayGraphRAG"
.\.venv\Scripts\Activate.ps1
```

실제 SQUID 가중치를 쓰려면 `scipy`가 설치되어 있어야 한다. 없으면 mock reconstruction으로 fallback된다.

```powershell
python -m pip install scipy
python scripts\verify_squid.py
```

아래 로그가 뜨면 실제 가중치를 못 쓰고 mock을 쓰는 상태다.

```text
[ml] torch anomaly model unavailable, falling back to mock: No module named 'scipy'
```

### 4.2. XrayGraphRAG DB 초기화

ArangoDB 컨테이너가 실행 중이어야 한다.

```powershell
python scripts\init_db.py
```

이 명령은 `xray_graph_db`에 컬렉션, 그래프, 기본 disease/ROI/finding 노드, 벡터 인덱스를 준비한다.

### 4.3. CheXpert train frontal 데이터 적재

train 데이터 중 frontal AP/PA를 모두 넣는 명령:

```powershell
python scripts\seed_chexpert.py `
  --archive "C:\Users\kjbdd\Downloads\archive" `
  --split train `
  --frontal-only `
  --uncertainty ones `
  --batch 100
```

현재 스크립트의 `--frontal-only`는 `Frontal/Lateral == Frontal`만 거른다. 이 안에는 `AP`, `PA`가 모두 포함되므로 `--view`를 생략하면 AP/PA가 함께 적재된다.

특정 view만 따로 적재하거나 확인하고 싶으면 `--view AP` 또는 `--view PA`를 사용한다.

처음 테스트할 때는 전체를 바로 넣지 말고 limit을 걸어 속도와 결과를 확인하는 것을 권장한다.

```powershell
python scripts\seed_chexpert.py `
  --archive "C:\Users\kjbdd\Downloads\archive" `
  --split train `
  --frontal-only `
  --limit 1000 `
  --uncertainty ones `
  --batch 100
```

### 4.4. 벡터 인덱스 재생성

CheXpert seed가 끝난 뒤 다시 실행한다.

```powershell
python scripts\init_db.py
```

데이터를 넣기 전에 만든 벡터 인덱스는 학습 샘플 부족으로 `not ready`가 될 수 있다. 따라서 seed 이후 재실행해야 의미가 있다.

`vector_supported=True`가 나오면 벡터 인덱스를 사용할 수 있다. `False`면 검색이 brute-force fallback으로 돌 수 있고, 데이터가 많을수록 inference가 느려질 수 있다.

### 4.5. seed 중단 / 재시작

진행 중인 seed는 `Ctrl + C`로 끊어도 된다. 이미 들어간 case는 DB에 남고, 아직 처리하지 않은 case만 안 들어간다.

주의: 같은 명령을 그대로 다시 실행하면 이미 들어간 이미지가 중복 등록될 수 있다. mock으로 잘못 넣었거나 처음부터 다시 넣고 싶으면 `xray_graph_db`만 비우고 다시 시작하는 것이 좋다.

## 5. 처방 추천용 ArangoDB 데이터 적재

처방 추천은 `bitcomputer_graph` DB를 사용한다. Docker volume을 삭제했거나 ArangoDB를 새로 만들었다면 다시 적재해야 한다.

### 5.1. 일반 output CSV 적재

```powershell
cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer\GraphDB\data_normalize"
python -m pip install -r requirements.txt

$env:ARANGO_HOST="localhost"
$env:ARANGO_PORT="8529"
$env:ARANGO_USER="root"
$env:ARANGO_PASSWORD="<YOUR_ARANGO_ROOT_PASSWORD>"
$env:ARANGO_DATABASE="bitcomputer_graph"

python import_to_arango.py --database bitcomputer_graph --batch 1000
```

기본 입력 디렉터리는 다음이다.

```text
GraphDB\data_normalize\output
```

필수 CSV가 없으면 먼저 normalize 스크립트를 실행해 `output/*.csv`를 생성해야 한다.

### 5.2. train/test split 그래프 적재

train/test용 output을 별도 DB에 넣고 싶으면 아래 스크립트를 쓴다.

```powershell
cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer\GraphDB\data_normalize"
python import_train_test_to_arango.py --only both --batch 1000
```

기본 DB 이름:

```text
train -> bitcomputer_graph_train
test  -> bitcomputer_graph_test
```

Spring/처방 추천 서비스가 사용할 DB는 `.env.docker`와 `docker-compose.yml`의 `ARANGO_DATABASE` 값과 맞아야 한다. 현재 기본은 `bitcomputer_graph`다.

## 6. 진단서 의사소견 데이터 준비

진단서 의사소견은 ArangoDB가 아니라 MySQL + LLM 게이트웨이(`services/llm-gateway`) 기반이다.

필요한 것:

- MySQL에 환자, 진료, 상병, 처방 데이터가 있어야 한다.
- certificate-api의 `LLM_GATEWAY_BASE_URL`은 `infra/docker-compose.yml`에 `http://llm-gateway:8003/v1`로
  고정되어 있어 env 파일로 바꿀 수 없다. env로 조정 가능한 값은 `LLM_MODEL`뿐이다 — 필요하면
  `infra/.env`에 넣는다. certificate-api는 Gemini를 직접 호출하지 않고 `services/llm-gateway`를
  경유한다.

확인:

```powershell
curl http://localhost:5001/health
```

`llm_gateway_configured`가 `true`여야 실제 게이트웨이 호출이 가능하다.

## 7. 처방 추천 / 진료 데이터 검증 에이전트

검증 에이전트는 프론트의 `AI 처방 추천` 버튼을 트리거로 동작한다. Spring Boot가 `validation_job`을 만들고 RabbitMQ request queue에 메시지를 발행하면, `validation-agent`가 메시지를 소비해 LangGraph/ReAct 기반 추천·검증 루프를 수행한 뒤 result queue로 결과를 반환한다.

동작 흐름:

1. 프론트에서 `AI 처방 추천` 버튼 클릭
2. Spring이 `validation_job`을 `PENDING`으로 생성
3. Spring이 RabbitMQ `validation.prescription.request` queue에 job 메시지 발행
4. `validation-agent`가 메시지를 소비하고 `RUNNING` 상태 이벤트 발행
5. ValidationAgent가 `Prescription Finder`, `X-ray Result Loader`, `Disease Validator`, `Prescription Validator`, `Pubmed Loader`를 사용해 ReAct 루프 수행
6. `PASS` 또는 최대 반복 횟수 도달 시 structured JSON result 생성
7. ValidationAgent가 RabbitMQ `validation.prescription.result` queue에 결과 발행
8. Spring consumer가 `validation_result`에 결과 JSON을 저장하고 `validation_job`을 `DONE` 또는 `FAILED`로 갱신
9. 프론트는 `/api/validation-jobs/{jobId}`를 polling하고, 완료되면 검증 완료 팝업과 추천 처방을 표시

관련 테이블:

| 테이블 | 역할 |
|---|---|
| `validation_job` | 비동기 job 상태 추적 (`PENDING`, `RUNNING`, `DONE`, `FAILED`) |
| `validation_result` | 최종 검증 결과 structured JSON 저장 |
| `validation_event` | 이전 outbox 방식 테이블. 현재 RabbitMQ job 흐름에서는 기본 비활성화 |

RabbitMQ queue:

| Queue | 역할 |
|---|---|
| `validation.prescription.request` | Spring -> ValidationAgent 추천/검증 요청 |
| `validation.prescription.result` | ValidationAgent -> Spring 상태/결과 반환 |

검증에 사용하는 데이터:

- `history`: 증상/진료 기록
- `history_disease`: 저장 상병
- `history_diagnose`: 저장 처방
- `radiology_report`: 같은 환자의 최신 완료 영상판독 결과
- `prescription-api`: 불일치 가능성이 있을 때 참고 처방 후보 조회
- PubMed API: 처방 근거 검색 보조

헬스 체크:

```powershell
curl http://localhost:8002/health
```

검증 결과 조회:

```powershell
curl "http://localhost:8080/api/validation-jobs/{jobId}"
```

결과 예시:

```json
{
  "jobId": "550e8400-e29b-41d4-a716-446655440000",
  "historyId": 1,
  "status": "DONE",
  "summary": "검증 가능한 범위에서 큰 불일치가 발견되지 않았습니다.",
  "result": {
    "overallStatus": "PASS",
    "recommendedPrescriptions": [],
    "reasoningTrace": []
  }
}
```

주요 설정:

| 설정 | 기본값 | 설명 |
|---|---|---|
| `VALIDATION_AGENT_BASE_URL` | `http://validation-agent:8002` | Docker 내부 Spring -> validation-agent 호출 주소 |
| `VALIDATION_SCHEDULER_ENABLED` | `false` | 이전 outbox scheduler 활성화 여부. RabbitMQ 흐름에서는 기본 비활성화 |
| `RABBITMQ_HOST` | `rabbitmq` | RabbitMQ host |
| `RABBITMQ_PORT` | `5672` | RabbitMQ AMQP port |
| `RABBITMQ_USERNAME` | `guest` | RabbitMQ 사용자 |
| `RABBITMQ_PASSWORD` | `guest` | RabbitMQ 비밀번호 |
| `VALIDATION_RABBITMQ_REQUEST_QUEUE` | `validation.prescription.request` | 추천/검증 요청 queue |
| `VALIDATION_RABBITMQ_RESULT_QUEUE` | `validation.prescription.result` | 추천/검증 결과 queue |
| `LLM_GATEWAY_BASE_URL` | `http://llm-gateway:8003/v1` | ValidationAgent 가 게이트웨이 경유로 LLM 을 호출하는 base URL. 자격증명은 게이트웨이가 가짐 |
| `LLM_MODEL` | `openai.gpt-5.6-luna` | ValidationAgent tool decider/PubMed 요약용 모델 |

검증 에이전트는 DB를 직접 수정하지 않는다. 상병/처방 자동 변경도 하지 않고, 의료진 검토용 결과만 `validation_result`에 저장한다.

## 8. Xray 영상판독 동작 확인

프론트 AI 리포트 화면에서는 분석 전 `PA` 또는 `AP` 촬영 방향을 선택할 수 있다. 선택한 값은 Spring을 거쳐 XrayGraphRAG의 `/infer` 요청 `view`로 전달된다.

XrayGraphRAG 직접 확인:

```powershell
curl.exe -X POST http://localhost:8000/infer `
  -F "image=@C:\Users\kjbdd\Downloads\archive\valid\patient64541\study1\view1_frontal.jpg" `
  -F "view=AP" `
  -F "topK=10"
```

Spring API 경유 확인:

```powershell
curl.exe -X POST http://localhost:8080/api/radiology/upload-and-analyze `
  -F "file=@C:\Users\kjbdd\Downloads\archive\valid\patient64541\study1\view1_frontal.jpg" `
  -F "patientId=1" `
  -F "employeeId=1" `
  -F "deptId=1" `
  -F "entryDate=2026-05-10" `
  -F "view=PA"
```

AP 데이터로 확인하려면 `view=AP`로 바꾼다. XrayGraphRAG DB에도 같은 view의 case가 적재되어 있어야 유사 case와 상병 후보가 나온다.

정상 응답 형태:

```json
{
  "heatmapUrl": "http://localhost:8000/storage/heatmaps/query_case_xxxx_heatmap.png",
  "predictedDiseases": [
    {
      "disease": "cardiomegaly",
      "score": 0.82,
      "reason": "..."
    }
  ],
  "warning": "이 결과는 의학적 진단이 아닙니다..."
}
```

`predictedDiseases`가 빈 배열이면 유사 case가 없거나, DB에 같은 view/modelVersion/maskVersion 조건의 case가 부족한 상태일 수 있다.

## 9. Docker build와 인덱싱의 관계

Docker build 시점에 ArangoDB 벡터 인덱싱을 하는 것은 의미가 없다.

- `docker build`: 앱 이미지 생성
- `seed_chexpert.py`: 실행 중인 ArangoDB volume에 Xray case 적재
- `init_db.py`: 실행 중인 ArangoDB에 컬렉션/그래프/벡터 인덱스 생성

올바른 순서:

```powershell
docker compose --env-file .env.docker up -d --build

cd "C:\Users\kjbdd\OneDrive\바탕 화면\Project\BitComputer\XrayGraphRAG"
.\.venv\Scripts\Activate.ps1

python scripts\init_db.py
python scripts\seed_chexpert.py --archive "C:\Users\kjbdd\Downloads\archive" --split train --frontal-only --uncertainty ones --batch 100
python scripts\init_db.py
```

## 10. 자주 쓰는 명령 요약

전체 실행:

```powershell
docker compose --env-file .env.docker up -d
```

전체 재빌드 후 실행:

```powershell
docker compose --env-file .env.docker up -d --build
```

MySQL 상병/처방 마스터 적재:

```powershell
python .\Back-End\scripts\import_master_codes.py
```

전체 종료, 데이터 유지:

```powershell
docker compose --env-file .env.docker down
```

전체 종료, 데이터 삭제:

```powershell
docker compose --env-file .env.docker down -v
```

상태 확인:

```powershell
docker compose --env-file .env.docker ps
```

Spring 로그:

```powershell
docker logs -f bit-spring-boot
```

검증 에이전트 로그:

```powershell
docker logs -f bit-validation-agent
```

RabbitMQ 관리 UI:

```text
http://localhost:15672
user: guest
password: guest
```

XrayGraphRAG 로그:

```powershell
docker logs -f bit-xraygraph
```

ArangoDB 웹 UI:

```text
http://localhost:8529
user: root
password: .env.docker의 ARANGO_PASSWORD
```
