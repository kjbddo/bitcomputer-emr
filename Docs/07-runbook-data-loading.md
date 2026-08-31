# 런북: 데이터 적재와 검증

빈 볼륨에서 시작해 화면에서 기능이 보이는 상태까지 가는 절차. 모든 명령은 저장소 루트 기준이고, 실행 순서가 곧 의존 순서다.

`Docs/05-data-and-deployment.md` 의 §9 가 이 문서로 대체됐다. 그 문서의 경로들은 모노레포 이전 것이라 더 이상 존재하지 않는다.

---

## 0. 왜 이 문서가 필요한가

**`docker compose up` 은 데이터를 만들지 않는다.** 이미지 빌드도, 컨테이너 기동도 마찬가지다. 스택이 전부 healthy 여도 DB 는 비어 있을 수 있고, 그러면 화면은 조용히 아무것도 못 한다 — 에러가 아니라 빈 목록으로.

실제로 겪은 증상:

| 비어 있는 것 | 화면에서 보이는 증상 |
|---|---|
| MySQL `disease` | 진료 화면에서 상병을 하나도 고를 수 없다 |
| MySQL `diagnose` | 처방 코드 조회가 전부 빈손 |
| Arango `bitcomputer_graph` | AI 처방 추천이 후보 없이 돌아 모든 검증이 `skipped`, 화면 전체가 "미검증" |
| Arango `xray_graph_db` 의 `xray_cases` | X-ray 유사 사례 검색이 항상 0건 |

마지막 줄이 특히 헷갈린다. 검증층은 근거가 없으면 `skipped` 를 내도록 설계돼 있어서(GC-2), **데이터가 없을 때와 검증층이 고장났을 때가 화면에서 똑같아 보인다.** 배지가 전부 "미검증"이면 먼저 이 런북부터 확인한다.

---

## 1. 사전 조건

- Docker Desktop 실행 중
- Python 3.12+ (이 문서의 명령은 `python` 으로 적는다. Windows 에서 `python3` 은 Microsoft Store 스텁으로 잡혀 **아무 일도 하지 않고 성공한 것처럼 출력하므로 쓰지 않는다.**)
- `pip install openpyxl pandas python-arango`
- `infra/.env` 존재. 없으면 `infra/.env.example` 을 복사해 값을 채운다

원본 엑셀 세 개는 저장소에 들어 있다:

| 파일 | 적재 대상 |
|---|---|
| `apps/api/상병코드.xlsx` | MySQL `disease` |
| `apps/api/처방코드.xlsx` | MySQL `diagnose` |
| `packages/graph-etl/20260406_상병별 처방코드 추출_특이사항 추가.xlsx` | Arango 처방 추천 그래프 |

X-ray 이미지(CheXpert)만 저장소 밖이다 — §5 참조.

---

## 2. 인프라 기동

```bash
cd infra && docker compose up -d
```

전부 healthy 가 될 때까지 기다린다:

```bash
docker ps --format "{{.Names}}\t{{.Status}}" | sort
```

`bit-frontend` 는 healthcheck 가 없어 `Up` 만 뜬다. 나머지 11개가 `(healthy)` 여야 한다.

---

## 3. MySQL 마스터 코드

상병·처방 마스터. **이게 없으면 진료 자체가 시작되지 않는다.**

```bash
cd apps/api
MYSQL_PASSWORD="$(grep '^MYSQL_ROOT_PASSWORD=' ../../infra/.env | cut -d= -f2-)" python scripts/import_master_codes.py
```

스크립트가 엑셀을 CSV 로 변환한 뒤(`apps/api/generated/master-codes/`) `bit-mysql` 컨테이너에 `LOAD DATA` 로 넣는다. 기본이 docker 모드라 컨테이너 이름만 맞으면 된다.

기대 출력:

```
[convert] disease: 50941 rows -> ...\disease_codes.csv
[convert] diagnose: 505954 rows -> ...\prescription_codes.csv
[import] disease: 50941 rows
[import] diagnose: 505954 rows
```

확인:

```bash
PW=$(grep '^MYSQL_ROOT_PASSWORD=' infra/.env | cut -d= -f2-)
docker exec bit-mysql sh -c "mysql -uroot -p'$PW' -N -e \"SELECT CONCAT('disease=',(SELECT COUNT(*) FROM bitcomputer.disease),' diagnose=',(SELECT COUNT(*) FROM bitcomputer.diagnose));\""
```

> **한글이 깨져 보이는 것은 대개 착시다.** Windows 콘솔 코드페이지가 UTF-8 이 아니면 `2형 당뇨병` 이 `2?? ????` 로 찍힌다. DB 안의 바이트를 직접 봐야 판단할 수 있다:
> ```bash
> docker exec bit-mysql sh -c "mysql -uroot -p'$PW' -N -B -e \"SELECT HEX(name) FROM bitcomputer.disease WHERE code='E11' LIMIT 1;\"" \
>   | tr -d '\r\n' | python -c "import sys,binascii; print(binascii.unhexlify(sys.stdin.read().strip()).decode('utf-8'))"
> ```
> 이게 `UnicodeDecodeError` 없이 나오면 데이터는 멀쩡하다.

---

## 4. 처방 추천 그래프 (ArangoDB)

AI 처방 추천의 후보 출처. **이게 없으면 B1 검증 배지가 전부 "미검증" 이 된다.**

### 4.1 엑셀 → 그래프 CSV

`packages/graph-etl/output/` 에 CSV 14개가 이미 있으면 건너뛴다.

```bash
cd packages/graph-etl
cp "20260406_상병별 처방코드 추출_특이사항 추가.xlsx" input/   # 이미 있으면 생략
python graph_normalize.py
```

노드 6종·관계 8종을 `output/` 에 UTF-8-SIG CSV 로 낸다. 산출물 규격은 `packages/graph-etl/GRAPH_CSV_가이드.md` 참조.

### 4.2 CSV → ArangoDB

```bash
cd packages/graph-etl
export ARANGO_HOST=localhost ARANGO_PORT=8529 ARANGO_USER=root ARANGO_DATABASE=bitcomputer_graph
export ARANGO_PASSWORD="$(grep '^ARANGO_PASSWORD=' ../../infra/.env | cut -d= -f2-)"
python import_to_arango.py
```

> **기본 동작은 컬렉션을 비우고 다시 넣는 것이다.** 기존 데이터를 남기려면 `--append` 를 붙인다. 연결 없이 건수만 세려면 `--dry-run`.

기대 출력(행 수는 원본에 따라 다름):

```
visits: 1070          order_lines: 6809        prescription_masters: 880
diagnoses: 9          special_notes: 1025      note_mentions: 4099
visit_has_diagnosis: 1150    visit_has_order: 6809
order_refers_prescription: 6809   order_associated_diagnosis: 7275
```

확인:

```bash
PW=$(grep '^ARANGO_PASSWORD=' infra/.env | cut -d= -f2-)
curl -s "http://localhost:8529/_db/bitcomputer_graph/_api/collection?excludeSystem=true" -u "root:$PW" \
  | python -c "import sys,json; print(len(json.load(sys.stdin)['result']),'collections')"
```

14가 나와야 한다.

### 4.3 이 그래프에 실제로 들어 있는 상병코드를 확인한다

**이 단계를 건너뛰면 안 된다.** 그래프의 상병코드 집합은 MySQL 마스터(50,941건)보다 훨씬 좁다. 그 밖의 상병으로 추천을 돌리면 후보가 빈손이라 모든 검사가 `skipped` 로 떨어지고, 화면은 고장난 것처럼 보인다.

```bash
curl -s -X POST "http://localhost:8529/_db/bitcomputer_graph/_api/cursor" -u "root:$PW" \
  -d '{"query":"FOR d IN diagnoses SORT d._key RETURN d._key"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['result'])"
```

현재 원본 기준으로 아홉 개다:

```
A15  C34  D50  E03  E11  E78  I10  J18  J90
```

화면에서 AI 추천을 시험할 때는 이 중 하나를 고른다. `E11`(2형 당뇨병)이 후보가 가장 많이 나와 확인하기 좋다.

---

## 5. X-ray 그래프 (CheXpert)

X-ray 유사 사례 검색용. **처방 추천·검증층과는 무관하므로, B1 만 확인할 목적이면 건너뛰어도 된다.**

CheXpert 는 Kaggle 계정 인증이 필요하고 약 11GB 다. 자동화하지 않는다.

### 5.1 스키마 초기화

```bash
cd services/xray-rag
python scripts/init_db.py
```

`diseases`·`findings`·`rois` 등 온톨로지 컬렉션을 만든다. 사례는 아직 0건이다.

### 5.2 CheXpert 내려받기

`kagglehub>=0.3` 은 `services/xray-rag/requirements.txt` 에 선택 의존으로 들어 있다. 따로 설치했다면:

```bash
pip install kagglehub
```

**토큰은 `infra/.env` 의 `KAGGLE_API_TOKEN` 에 둔다.** 발급은 Kaggle 계정 페이지의 Settings → API → Create New Token. 값 자체를 넣어도 되고 토큰이 담긴 파일 경로를 넣어도 된다.

적재는 컨테이너가 아니라 호스트에서 돌기 때문에 compose 가 이 값을 실어주지 않는다. 셸에 직접 올린다:

```bash
cd services/xray-rag
export KAGGLE_API_TOKEN="$(grep '^KAGGLE_API_TOKEN=' ../../infra/.env | cut -d= -f2-)"
python scripts/download_chexpert.py --dest ./archive
```

`kagglehub` 는 `KAGGLE_API_TOKEN` 을 `~/.kaggle/kaggle.json` 보다 **먼저** 읽는다(`kagglehub.config.get_kaggle_credentials`). 둘 다 있으면 환경변수가 이긴다. 배선만 먼저 확인하려면:

```bash
python -c "import kagglehub.config as c; print(c.get_access_token_from_env())"
```

`('<토큰>', 'KAGGLE_API_TOKEN')` 이 나오면 인증 경로가 살아 있는 것이다. `(None, None)` 이면 export 가 안 된 것이다.

`--dest` 는 기본이 junction(Windows)/symlink(POSIX)이라 디스크를 추가로 쓰지 않는다. `--mode copy` 는 11GB 이상을 더 쓴다.

### 5.3 벡터 인덱스 차원을 먼저 확인한다

**`init_db.py` 는 이미 있는 인덱스를 `exists` 로 그냥 통과시킨다.** 차원이 달라도 다시 만들지 않는다. 임베딩 모델을 바꿨다면(현재 DenseNet121, 1024차원) 예전 차원의 인덱스가 남아 벡터와 어긋난다.

```bash
PW=$(grep '^ARANGO_PASSWORD=' infra/.env | cut -d= -f2-)
curl -s "http://localhost:8529/_db/xray_graph_db/_api/index?collection=xray_cases" -u "root:$PW" \
  | python -c "
import sys,json
for ix in json.load(sys.stdin).get('indexes',[]):
    if ix.get('type')=='vector':
        print(ix.get('name'),'dim=',(ix.get('params') or {}).get('dimension'))
"
```

`dim=1024` 가 아니면 지우고 다시 만든다. **케이스가 이미 있으면 그 벡터도 전부 무효가 되므로 `xray_cases` 가 0인지 먼저 본다.**

```bash
IDS=$(curl -s "http://localhost:8529/_db/xray_graph_db/_api/index?collection=xray_cases" -u "root:$PW" \
  | python -c "
import sys,json
print(' '.join(ix['id'] for ix in json.load(sys.stdin).get('indexes',[]) if ix.get('type')=='vector'))
")
for id in $IDS; do curl -s -X DELETE "http://localhost:8529/_db/xray_graph_db/_api/index/$id" -u "root:$PW" -o /dev/null; done
python scripts/init_db.py    # 이번에는 status=created 로 나와야 한다
```

### 5.4 시드

**실제 모델로 적재한다.** `--use-real-model` 은 SQUID 이상탐지만 켠다 — 임베딩까지 실제 모델로 하려면 `USE_TORCH_EMBEDDING=true` 를 함께 준다.

**`seed_chexpert.py` 는 덮어쓰지 않고 "추가"한다.** 이미 등록된 상태에서 다시 돌리면
같은 202건이 새 `_key` 로 한 벌 더 들어가고, 모델을 바꿨다면 두 세대의 벡터가 한
컬렉션에 섞인다. 재시드라면 먼저 비운다:

```bash
PW=$(grep '^ARANGO_PASSWORD=' infra/.env | cut -d= -f2-)
for c in xray_cases case_has_disease case_has_finding case_has_roi_anomaly; do
  curl -s -X PUT "http://localhost:8529/_db/xray_graph_db/_api/collection/$c/truncate" -u "root:$PW" -o /dev/null
done
```

```bash
cd services/xray-rag
export ARANGO_HOST=localhost ARANGO_PORT=8529 ARANGO_USER=root XRAY_ARANGO_DATABASE=xray_graph_db
export ARANGO_PASSWORD="$(grep '^ARANGO_PASSWORD=' ../../infra/.env | cut -d= -f2-)"
export USE_TORCH_EMBEDDING=true
python scripts/seed_chexpert.py --archive ./archive --split valid --frontal-only --uncertainty ones --batch 25 --use-real-model
```

`valid` 는 202건에 약 6분(0.59 rows/s)이다. `train` 은 훨씬 크므로 수 시간을 예상한다.

확인 — 건수만 보지 말고 **무엇이 저장됐는지** 본다:

```bash
curl -s -X POST "http://localhost:8529/_db/xray_graph_db/_api/cursor" -u "root:$PW" \
  -d '{"query":"FOR c IN xray_cases LIMIT 1 RETURN {v:c.embeddingVersion, dim:LENGTH(c.globalErrorEmbedding)}"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['result'][0])"
```

기대: `{'v': 'densenet121_imagenet_1024', 'dim': 1024}`

`v` 가 `mock_pca_v1` 이면 임베딩이 mock 으로 돌았다는 뜻이다 — `USE_TORCH_EMBEDDING` 을 안 줬거나 가중치 로드에 실패했다. 건수만 확인하고 넘어가면 이걸 놓친다.

### 5.5 컨테이너도 같은 모델을 올려야 한다

**시드를 실제 모델로 했으면 질의도 같은 모델이어야 한다.** error map 이 달라지면 임베더가 같아도 벡터가 비교 불가능해져, 유사 검색이 조용히 엉뚱한 결과를 낸다.

컨테이너가 무엇을 올렸는지 확인한다:

```bash
docker exec bit-xraygraph python -c "
from app.config import get_settings
from app.ml.factory import build_models
r = build_models(get_settings())
print('anomaly_is_real  ', r.anomaly_is_real)
print('embedding_is_real', r.embedding_is_real)
print('engine_status    ', r.engine_status)
print('embedding_version', r.embedding_version)
print('dim              ', r.embedder.dim)
print('roi_status       ', r.roi_status)
print('mask_version     ', r.mask_version)
"
```

기대: `engine_status real`, `dim 1024`, `embedding_version densenet121_imagenet_1024`,
`roi_status pspnet`, `mask_version pspnet_chestxdet_v1`.

`roi_status` 는 **일부러 `engine_status` 에 섞지 않았다**(이유는 `app/ml/factory.py` 의
`BuildResult` 독스트링). 값이 셋이고 각각 다른 뜻이다.

| `roi_status` | 무엇이 올라왔나 | `mask_version` |
|---|---|---|
| `pspnet` | ChestX-Det PSPNet — 학습된 해부학 분할 모델. **이것이 기대값이다** | `pspnet_chestxdet_v1` |
| `cv` | 고전 CV 분할. 영상에 적응하지만 학습된 모델은 아니다 — PSPNet 가중치가 없으면 여기로 내려온다(§5.7) | `cv_lung_heart_v1` |
| `mock` | 입력과 무관한 고정 타원. ROI별 임베딩이 해부학과 무관해진다 | `mock_ellipse_mask_v1` |

셋 다 서비스는 뜬다. **조용히 내려갈 뿐이다** — 그래서 이 확인을 건너뛰면 안 된다.
다만 내려간 사실 자체는 WARNING 로그와 이 값에 남으므로, real 인 척하지는 않는다.
ROI별 임베딩(`--use-roi`)과 `roiStats` 의 의미가 이 값에 달려 있다 — 시드와 질의가
서로 다른 분할기면 `maskVersion` 이 같아도 ROI 벡터는 비교 불가능하다. 케이스 문서의
`roiMaskVersion` 으로 어느 쪽으로 시드됐는지 확인할 수 있다.

기대와 다르면 아래 다섯 중 하나가 빠진 것이다. `infra/docker-compose.yml` 의
`xraygraph` 블록을 본다.

| 필요한 것 | 없으면 |
|---|---|
| SQUID 가중치 마운트 (`services/radiology-legacy` 통째로) | 로더가 부모에서 `config.py` 를 찾으므로 가중치 폴더만 주면 깨진다 |
| 호스트 torch 캐시 마운트 | 컨테이너에 egress 가 없어 DenseNet 가중치를 못 받는다 |
| **호스트 torchxrayvision 캐시 마운트** | 같은 이유로 PSPNet 가중치를 못 받는다 → `roi_status` 가 `cv` 로 내려간다(§5.7) |
| `scipy`·`opencv-python-headless`·`matplotlib`·`tqdm`·`torchxrayvision` | SQUID 로더 / PSPNet 어댑터가 import 에서 실패한다 |
| `USE_TORCH_ANOMALY`·`USE_TORCH_EMBEDDING`·`USE_PSPNET_ROI`·`EMBEDDING_DIM` | 토글이 꺼져 있거나 차원이 어긋난다 |

`engine_status` 가 `mock` 이라고 서비스가 죽지는 않는다. **조용히 mock 으로 돌 뿐이다** — 그래서 이 확인을 건너뛰면 안 된다. 다만 `engine_status` 는 토글이 아니라 실제로 구성된 모델을 근거로 판정하므로, real 인 척하지는 않는다.

### 5.6 종단 확인

실제 이미지로 추론을 돌려 유사 사례가 나오는지 본다:

```bash
IMG=$(ls services/xray-rag/archive/valid/*/*/*.jpg | head -1)
curl -s -X POST http://localhost:8000/infer -F "image=@$IMG" -F "view=PA" -m 240 -o infer_out.json -w "http=%{http_code}\n"
python -c "
import json
d=json.load(open('infer_out.json',encoding='utf-8'))
print('engineStatus:', d['engineStatus'])
print('similarCases:', len(d['similarCases']))
print('top sim:', round(float(d['similarCases'][0]['similarity']),4))
"
rm -f infer_out.json
```

`similarCases` 가 0이면 인덱스 차원과 질의 벡터 차원이 어긋난 것이다(§5.3).

### 5.7 PSPNet ROI 가중치 — 호스트에서 받아 컨테이너에 마운트한다

ROI 분할기가 ChestX-Det PSPNet 으로 바뀌었다(EVALUATION.md §11). 가중치는
**273MB** 이고 패키지에 들어 있지 않다. **컨테이너에는 egress 가 없다** — DenseNet
가중치와 똑같은 상황이고, 해법도 똑같다: 호스트에서 받아 그 디렉터리를 마운트한다.

어댑터는 기본적으로 런타임 다운로드를 하지 않는다(`PSPNET_ALLOW_DOWNLOAD=false`).
켜두면 egress 없는 컨테이너에서 기동이 네트워크 타임아웃만큼 멈춘다. 파일이 이미
있을 때만 올리고, 없으면 즉시 다음 후보(`cv`)로 내려간다.

**호스트에서 한 번:**

```bash
cd services/xray-rag
python scripts/fetch_pspnet_weights.py
# -> ~/.torchxrayvision/models_data/pspnet_chestxray_best_model_4.pth (260MB)
#    sha256 019b167eac6b729fc1bb92bbbc185fc1730aaa65819f4e3fe718186cadc044fc
```

스크립트는 sha256 을 검증한다. 상류 릴리스가 같은 파일명으로 다른 가중치를 올리면
거기서 걸린다 — 조용히 다른 모델로 바뀌는 것이 제일 피해야 할 사고다.

이미 받았는지만 보려면 `--verify-only` 를 준다.

**컨테이너 쪽 — `infra/docker-compose.yml` 의 `xraygraph` 블록에 넣어야 할 변경.**
이 파일은 infra 소유라 여기서 바꾸지 않았다. 아래를 적용해야 컨테이너의
`roi_status` 가 `pspnet` 이 된다.

```yaml
    environment:
      # ...기존 유지...
      USE_PSPNET_ROI: ${USE_PSPNET_ROI:-true}
      # 아래 마운트 경로와 반드시 같아야 한다. 비워두면 어댑터가
      # ~/.torchxrayvision/models_data 를 보는데 컨테이너의 그 경로는 비어 있다.
      PSPNET_CACHE_DIR: /root/.torchxrayvision/models_data
      # egress 가 없다. true 로 두면 기동이 타임아웃만큼 멈춘다.
      PSPNET_ALLOW_DOWNLOAD: "false"
    volumes:
      # ...기존 유지...
      # ChestX-Det PSPNet 가중치 캐시. 없으면 ROI 가 cv 분할로 내려간다
      # (조용히는 아니고 WARNING + roi_status="cv").
      - ${PSPNET_HOST_CACHE_DIR:-~/.torchxrayvision/models_data}:/root/.torchxrayvision/models_data:ro
```

`torchxrayvision` 이 `services/xray-rag/requirements.txt` 에 추가됐으므로
**이미지 재빌드가 필요하다**(`docker compose build xraygraph`). 의존으로
`scikit-image` 계열이 함께 들어와 이미지가 커진다.

같은 블록의 `USE_TORCH_ROI: "false"` 는 이제 읽는 곳이 없다. 지워도 되고 둬도
동작에는 영향이 없다.

`MASK_VERSION: lung_heart_mask_v1` 고정은 **그대로 둔다.** 이것은 비교 대상을 정하는
운영 키이지 분할기 유래 값이 아니다. 모델 유래 값으로 바꾸면 컨테이너 `/infer` 가
0건을 반환한다(시드된 케이스의 `maskVersion` 과 어긋나기 때문). 분할기 식별자는
케이스 문서의 `roiMaskVersion` 에 따로 저장된다.

**적용 후 확인:** §5.5 의 `docker exec` 명령이 `roi_status pspnet`,
`mask_version pspnet_chestxdet_v1` 을 내야 한다.

---

## 6. 검증

적재가 끝났으면 아래 순서로 확인한다. 위에서 아래로 갈수록 더 깊은 경로를 지난다.

### 6.1 엔드포인트

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

### 6.2 그래프 후보가 실제로 조회되는지 — B1 의 핵심 경로

그래프에 있는 상병코드로 만든 시나리오를 그대로 태운다:

```bash
python -c "
import json
o=json.loads(open('services/prescription/evals/scenarios/arango_graph_prescription_eval_scenarios_27.jsonl',encoding='utf-8').readline())
open('probe.json','w',encoding='utf-8').write(json.dumps(o['request'],ensure_ascii=False))
"
curl -s -X POST http://localhost:8001/api/agent/prescription/recommend \
  -H "Content-Type: application/json" --data-binary @probe.json -m 300 -o probe_out.json
python -c "
import json
d=json.load(open('probe_out.json',encoding='utf-8'))
v=d['verification']
lines=[f\"llmStatus={d['llmStatus']} cohort={d['cohort_rx_count']} top_rx={d['arango_top_rx_count']}\",
       f\"status={v['status']}\"]
lines += [f\"  {c['id']:20s} {c['target']:15s} {c['outcome']}\" for c in v['checks']]
open('probe_report.txt','w',encoding='utf-8').write('\n'.join(lines))
"
cat probe_report.txt && rm -f probe.json probe_out.json probe_report.txt
```

> 결과를 파일로 쓰고 `cat` 하는 이유: 응답에 서로게이트 문자가 섞이면 콘솔로 바로 출력할 때 `UnicodeEncodeError` 가 난다. 파일 경유가 안전하다.

적재가 제대로 됐을 때:

```
llmStatus=real cohort=9 top_rx=6
status=passed
  schema_top3          response        ok
  code_in_candidates   prescription[1] ok
  name_matches_code    prescription[1] ok
  confidence_in_range  prescription[1] ok
  ... prescription[2], prescription[3] 동일
```

읽는 법:

- `cohort`/`top_rx` 가 **0 이면 그래프 적재가 안 된 것이다** — §4 로 돌아간다
- `code_in_candidates` 가 `skipped` 면 대조할 후보가 없었다는 뜻이다. 검증층 고장이 아니라 데이터 부재다
- `confidence_in_range` 가 전부 `skipped` 면 Arango co-occurrence 조회가 빈손이다. 대개 그래프에 없는 상병코드를 쓴 경우다(§4.3)
- `llmStatus` 가 `real` 이 아니면 게이트웨이나 `LLM_API_KEY` 문제다. 검증층과 무관하다

### 6.3 전체 시나리오 계측 (선택)

```bash
cd services/prescription
python scripts/measure_verification.py evals/scenarios/arango_graph_prescription_eval_scenarios_27.jsonl
```

27건을 실제 모델에 태워 검사별 분포를 센다. 몇 분 걸리고 실제 API 비용이 발생한다. `flagged` 가 나오면 근거 문자열 전문을 함께 출력한다.

### 6.4 화면

http://localhost:3000

`.env` 의 `BOOTSTRAP_SUPERUSER_PASSWORD` 로 만들어진 계정으로 로그인한 뒤:

1. 진료 화면에서 상병을 §4.3 의 아홉 개 중 하나로 고른다
2. AI 처방 추천 실행
3. 추천 표의 각 행에 검증 배지, 표 위에 요약 줄 두 개(항목 단위 / 응답 단위)가 뜬다
4. 처방 선택기로 한 행을 다른 처방으로 바꾸면 **그 행만** 즉시 "미검증" 으로 떨어져야 한다. 배지가 그대로면 이전 처방 기준의 판정이 남아 있는 것이고, 그건 결함이다

---

## 7. 자주 겪는 함정

**이미지가 코드보다 오래됐다.** compose 는 소스를 마운트하지 않고 이미지에 굽는다. 코드를 고쳤으면 `docker compose build <service>` 없이는 반영되지 않는다. 화면 동작이 코드와 안 맞으면 이것부터 의심한다:

```bash
docker images --format "{{.Repository}}\t{{.CreatedAt}}" | grep "^infra-"
```

**`python3` 은 쓰지 않는다.** Windows 에서 Microsoft Store 스텁에 잡히면 아무 일도 하지 않고 성공한 것처럼 끝난다. 실제로 이 저장소에서 잘못된 측정 결과를 한 번 만들어냈다.

**`docker compose down` 은 데이터를 지우지 않는다.** 볼륨을 지우면 이 런북을 §3 부터 전부 다시 돌려야 한다.

**진단서 평가(`/api/agent/document/evaluate`)는 게이트웨이를 거치지 않으며, 지금은 죽어 있다.** `CertificateEvaluationServiceImpl` 이 Gemini 를 직접 호출하며 `GEMINI_API_KEY` 를 따로 요구하는데 그 키가 폐기됐다. 이 엔드포인트를 쓰는 화면(`apps/web/src/app/evaluation`)은 어디에서도 링크되지 않으므로 적재 검증 경로에는 영향이 없다. 다른 AI 기능은 전부 게이트웨이 경유다.

**모든 배지가 "미검증" 이라고 검증층을 의심하기 전에** §4.3 의 상병코드부터 확인한다. 그래프 밖의 상병이면 검증층은 정상 동작 중이며 근거가 없다고 정직하게 말하는 것이다.
