# Retrieval / Disease Inference Evaluation

> CheXpert valid (frontal) 202건 + smoke 3건 = **205건**을 ArangoDB 에 등록한 뒤
> Leave-One-Out 방식으로 reconstruction-error embedding 기반 retrieval 과 weighted voting
> disease prediction 의 성능을 측정한 결과입니다.
>
> **본 결과는 의학적 진단을 대체하지 않습니다.** 시스템의 *유사 사례 검색* 능력에 대한
> 정량적 측정이며, 임상 의사결정 보조 자료로만 해석되어야 합니다.

> **§1~§7 은 2026-05-07 mock 임베딩(dim=768) 기준이다.** 현재 임베딩은
> DenseNet121 사전학습(dim=1024)이고 재측정 결과는 **[§8](#8-densenet121-재측정-2026-08-30)**
> 에 있다. §2 의 지표를 현재 성능으로 읽지 않는다. §8.2 는 그 지표들이
> 다수 라벨 기준선과 같다는 것도 함께 보여준다.

## 1. 실험 설정

| 항목 | 값 |
| --- | --- |
| 데이터 | CheXpert v1.0-small valid (frontal only) + smoke 3건 |
| 등록 케이스 | 205 |
| 평가 대상(라벨 ≥1) | 174 |
| No Finding 으로 라벨 비어있는 케이스 | 31 (평가 제외) |
| Reconstruction model | SQUID `ae_squid_v1` (실제 학습 가중치) |
| Anomaly score | reconstruction-error pixel map → ROI별 mean / max / p95 / std |
| ROI mask | mock 휴리스틱(타원 기반 lungs/heart/pleural/upper-lower split) |
| Embedding | `mock_pca_v1` (deterministic random projection, dim=768, L2-normalized) |
| Similarity | cosine, view+modelVersion 일치 케이스끼리 비교 |
| Self exclusion | LOO (대각성분 -∞) |
| 평가 시점 | 2026-05-07 |

> ROI mask 와 embedding 은 현재 mock 단계입니다. 실제 segmentation/contrastive
> embedding 모델로 교체하면 minority disease 의 retrieval 성능이 크게 개선될 여지가
> 있습니다.

## 2. 핵심 결과 비교

`scripts/eval_retrieval.py` 두 가지 모드:

- **Global**: `globalErrorEmbedding` 만 사용 (`--use-roi` 미지정)
- **Global+ROI**: `0.5*global + 0.2*right_lung + 0.2*left_lung + 0.1*heart` 가중합 (`--use-roi`)

| metric | Global | Global+ROI | 변화 |
| --- | ---: | ---: | ---: |
| Hit@1 | 0.7184 | **0.7529** | +0.034 |
| Hit@3 | **0.9425** | 0.9368 | -0.006 |
| Hit@5 | 0.9483 | **0.9655** | +0.017 |
| Hit@10 | **0.9885** | 0.9828 | -0.006 |
| Hit@20 | 1.0000 | 1.0000 | = |
| Precision@1 | 0.7184 | **0.7529** | +0.034 |
| Precision@5 | 0.7345 | **0.7471** | +0.013 |
| MRR | 0.8277 | **0.8442** | +0.016 |
| mAP | **0.7532** | 0.7516 | -0.002 |
| Top-1 disease (any-match) | 0.6034 | **0.6264** | +0.023 |
| Top-3 disease (any-match) | **0.9598** | 0.9540 | -0.006 |

요점

- **Top-1 retrieval / disease prediction 모두 ROI 가중합이 우세**합니다. ROI mask 가
  mock 임에도 첫 번째 검색 결과의 정확도를 +3.4%p 끌어올리는 것은 reconstruction-error
  의 *공간 분포* 정보가 의미 있는 신호임을 시사합니다.
- 반면 Hit@10 / mAP 는 거의 동일하거나 미세하게 감소합니다. 잘못 정렬된 minority 라벨에
  대한 "넓은 범위 검색" 측면에서는 global-only 가 살짝 우세합니다.
- Hit@20 = 1.0 은 자기 자신을 제외해도 항상 같은 라벨을 공유하는 케이스가 20위 안에 1개
  이상 들어온다는 의미입니다. CheXpert valid 의 라벨 분포가 매우 편향되어 있어
  ("lung_opacity" 119/174, "support_devices" 100/174 등) 우연 수준이 높음을 함께 봐야
  합니다.

## 3. Per-disease recall (top-K voting)

| disease | n | recall@1 (G) | recall@3 (G) | recall@1 (G+ROI) | recall@3 (G+ROI) |
| --- | ---: | ---: | ---: | ---: | ---: |
| lung_opacity | 119 | 0.563 | **0.992** | 0.586 | 0.983 |
| enlarged_cardiomediastinum | 107 | 0.252 | 0.907 | **0.318** | **0.953** |
| support_devices | 100 | 0.110 | 0.810 | **0.130** | **0.860** |
| atelectasis | 75 | 0.000 | 0.107 | 0.000 | 0.080 |
| cardiomegaly | 67 | 0.000 | 0.134 | 0.000 | 0.179 |
| pleural_effusion | 64 | 0.000 | 0.031 | 0.000 | 0.063 |
| edema | 43 | 0.000 | 0.023 | 0.000 | 0.047 |
| consolidation | 32 | 0.000 | 0.000 | 0.000 | 0.000 |
| pneumonia | 8 | 0.000 | 0.000 | 0.000 | 0.000 |
| pneumothorax | 7 | 0.000 | 0.000 | 0.000 | 0.000 |
| lung_lesion | 1 | 0.000 | 0.000 | 0.000 | 0.000 |
| pleural_other | 1 | 0.000 | 0.000 | 0.000 | 0.000 |

해석

- 다수 라벨(lung_opacity / enlarged_cardiomediastinum / support_devices)은 weighted voting
  으로 의미 있게 회수됩니다. ROI 가중합은 enlarged_cardiomediastinum 의 recall@3 을
  +4.6%p, support_devices 의 recall@3 을 +5.0%p 끌어올립니다.
- minority 라벨(consolidation 이하 n ≤ 32)은 사실상 회수 불가입니다.
  - 평가 데이터 자체에서 이 라벨을 가진 사례가 매우 적어 이웃 후보가 부족합니다.
  - mock embedding 이 disease-discriminative 하지 않습니다 (random projection).
  - **개선 방향**: contrastive / supervised pretrained encoder 도입, holdout 셋을 늘려
    minority 라벨의 query/target 모두 충분히 확보, ROI segmentation 정합성 강화.

## 4. ROI severity / finding tag 분포

전체 205 케이스 기준 (No Finding 포함):

| roi | low | medium | high |
| --- | ---: | ---: | ---: |
| full_lung | 19 | 181 | 5 |
| heart | 71 | 133 | 1 |
| left_lung | 21 | 179 | 5 |
| lower_left_lung | 52 | 144 | 9 |
| lower_right_lung | 66 | 131 | 8 |
| mediastinum | 100 | 103 | 2 |
| pleural_region | 23 | 171 | 11 |
| right_lung | 23 | 177 | 5 |
| upper_left_lung | 11 | 188 | 6 |
| upper_right_lung | 7 | 191 | 7 |

- pleural_region 에서 high 비율이 가장 높습니다 (11/205). pleural_effusion / pneumothorax
  와 같은 흉막 병변에 대해 **공간 분포 특징** 자체는 적절히 잡고 있다는 신호이며,
  embedding 만 강화되면 retrieval 정확도가 크게 개선될 가능성이 큽니다.
- heart 는 high 가 1/205 로 매우 보수적입니다. cardiomegaly recall 이 낮은 이유 중 하나로,
  현재 mock 휴리스틱이 심장 영역을 과대 추정하고 있음을 시사합니다.

자동 생성된 finding tag (severity-rule 기반):

| finding | count |
| --- | ---: |
| bilateral_diffuse_error | 174 |
| pleural_region_high_error | 11 |
| left_lower_lung_high_error | 9 |
| right_lower_lung_high_error | 8 |
| right_upper_lung_high_error | 7 |
| left_upper_lung_high_error | 6 |
| right_lung_high_error | 5 |
| left_lung_high_error | 5 |
| mediastinum_high_error | 2 |
| cardiac_region_high_error | 1 |

> `bilateral_diffuse_error` 가 174건으로 압도적입니다. 현재 임계값(`MEDIUM_RATIO`)이
> SQUID error map 의 평균 분포에 비해 다소 낮게 설정되어 있어 거의 모든 케이스가
> "양측 확산" 으로 분류됩니다. 향후 임계값을 데이터 분포 기반(예: percentile 80-90)으로
> 조정하면 finding tag 의 specificity 가 상승할 것입니다.

## 5. 한계와 다음 단계

- **LOO 평가**: holdout 분리 평가가 아니므로 외부 일반화 성능은 측정할 수 없습니다.
  CheXpert train (201,055장)에서 holdout 1만건을 등록하고 valid 셋으로 query 하는 본격
  평가가 필요합니다.
- **Mock embedding**: random projection은 disease-aware 하지 않습니다. SimCLR /
  MoCo / MAE 류 pretrained encoder 또는 finding-supervised metric learning 도입이
  필수입니다.
- **Mock ROI mask**: 타원 기반 휴리스틱은 자세 회전 / cropping 에 취약합니다. 같은 저장소
  안의 `XrayGraphRAG/HybridGNet` 또는 외부 lung segmentation 모델 어댑터 추가가 다음
  단계입니다.
- **클래스 불균형**: minority 라벨(consolidation 이하)은 데이터 자체가 부족합니다.
  pretrain 단계에서 보강하거나, holdout 셋을 확대해야 의미 있는 측정이 가능합니다.
- **중복 케이스**: top-1 similarity ≥ 0.999 인 query 가 6건 검출되었습니다 (LOO 에서
  매우 동일한 영상이 다중 등록된 경우). 운영 단계에서는 등록 직전 dedupe 로직이
  필요합니다.

## 6. 재현 방법

```bash
# global only
python scripts/eval_retrieval.py
# global + ROI 가중합
python scripts/eval_retrieval.py --use-roi
# 특정 view 만
python scripts/eval_retrieval.py --view PA
```

각 실행은 `storage/eval/<timestamp>/` 또는 `--out` 경로에 다음 두 파일을 남깁니다.

- `metrics.json`: 메타 + 전체 metric + population 통계
- `report.md`: 사람이 바로 읽을 수 있는 자동 보고서

## 7. 안전 안내

본 시스템과 평가 결과는 **의학적 진단을 대체하지 않습니다**. AI 기반 후보 추론 시스템
(reconstruction-error pattern + case-based reasoning + graph reasoning) 의 정량적
재현성 측정 자료이며, 임상 의사결정에는 영상의학 전문의의 판독이 반드시 선행되어야
합니다.

---

## 8. DenseNet121 재측정 (2026-08-30)

임베딩을 `mock_pca_v1`(seed 고정 random projection, dim=768)에서 **DenseNet121 ImageNet 사전학습 frozen feature extractor**(dim=1024)로 교체한 뒤 다시 측정했다. reconstruction 모델(SQUID)과 ROI mask(mock 휴리스틱)는 그대로다.

| 항목 | 값 |
| --- | --- |
| 등록 케이스 | 202 (CheXpert valid frontal, smoke 없음) |
| 평가 대상(라벨 ≥1) | 146 |
| Embedding | `densenet121_imagenet_1024` |
| 실행 | `python scripts/eval_retrieval.py` (global only) |
| 산출물 | `storage/eval/20260830_143932/` |

> **§1~§3 의 2026-05-07 수치와 모집단이 다르다.** 그때는 205건/174건 평가에 `support_devices` 라벨이 포함돼 있었고, 이번에는 202건/146건에 그 라벨이 없다. 절대 수치를 직접 빼서 비교하면 안 되고, **경향**만 본다.

### 8.1 지표

| metric | mock_pca_v1 (768) | densenet121 (1024) |
| --- | ---: | ---: |
| Hit@1 | 0.7184 | 0.7534 |
| Hit@3 | 0.9425 | 0.9315 |
| MRR | 0.8277 | 0.8472 |
| mAP | 0.7532 | 0.7248 |
| Top-1 disease (any-match) | 0.6034 | 0.8014 |
| Top-3 disease (any-match) | 0.9598 | 0.9658 |

### 8.2 이 숫자들이 뜻하지 않는 것

**Top-1 any-match 0.8014 는 다수 라벨 기준선과 소수점 넷째 자리까지 같다.**

평가 대상 146건 중 `lung_opacity` 를 가진 케이스가 117건이다. 즉 **아무것도 검색하지 않고 항상 `lung_opacity` 하나만 답해도 0.8014** 가 나온다.

| | 값 |
| --- | ---: |
| 기준선: 항상 `lung_opacity` | 0.8014 |
| 실측 top-1 any-match | 0.8014 |
| 기준선: 항상 빈도 상위 3개 | 0.9795 |
| 실측 top-3 any-match | 0.9658 |

top-3 는 오히려 기준선보다 낮다.

원인은 평가 정의에 있다. multi-label 에서 relevance 를 "라벨 집합의 교집합 ≠ ∅" 로 정의하면, 한 라벨이 80% 에 붙어 있는 분포에서는 **아무 이웃이나 뽑아도 겹칠 확률이 높다.** MRR 0.847 / mAP 0.725 / Hit@1 0.753 은 그 확률을 재고 있는 것이지 질환 변별력을 재는 것이 아니다.

기준선 대조 없이 이 지표만 보면 시스템이 하지 않은 일을 했다고 읽게 된다.

### 8.3 per-disease recall — 무엇이 바뀌고 무엇이 안 바뀌었나

| disease | n | recall@1 mock → dense | recall@3 mock → dense |
| --- | ---: | --- | --- |
| lung_opacity | 117 | 0.563 → 0.667 | 0.992 → 1.000 |
| enlarged_cardiomediastinum | 105 | 0.252 → 0.371 | 0.907 → 0.933 |
| atelectasis | 75 | 0.000 → **0.000** | 0.107 → **0.467** |
| cardiomegaly | 66 | 0.000 → **0.000** | 0.134 → 0.121 |
| pleural_effusion | 64 | 0.000 → **0.000** | 0.031 → **0.453** |
| edema | 42 | 0.000 → **0.000** | 0.023 → 0.048 |
| consolidation | 32 | 0.000 → **0.000** | 0.000 → **0.000** |
| pneumonia | 8 | 0.000 → 0.000 | 0.000 → 0.000 |
| pneumothorax | 7 | 0.000 → 0.000 | 0.000 → 0.000 |

**나아진 것:** `atelectasis` recall@3 0.107 → 0.467, `pleural_effusion` 0.031 → 0.453. 중위권 검색에서 실제 이득이 있다.

**안 바뀐 것:** 다수 라벨 둘을 뺀 **아홉 개 질환 전부 recall@1 이 여전히 0.000** 이다. 1등 자리는 그대로 다수 라벨이 가져간다.

### 8.4 그래서 병목은 임베딩이 아니었다

§3 의 해석은 minority 라벨 회수 실패의 원인으로 "mock embedding 이 disease-discriminative 하지 않다(random projection)" 를 들고, 개선 방향으로 "contrastive / supervised pretrained encoder 도입" 을 제시했다.

**사전학습 encoder 로 바꿨는데 recall@1 은 한 라벨도 0.000 에서 벗어나지 못했다.** 그 진단은 부분적으로만 맞았다 — 임베딩 교체는 중위권(recall@3)을 올렸지만 1등 자리를 바꾸지 못했다.

남은 후보는 셋이고, 이번 측정으로 좁혀지지 않는다:

- **ROI mask 가 여전히 mock** 이다(타원 휴리스틱). ROI별 임베딩이 해부학적으로 어긋나 있으면 공간 정보가 잡음이 된다. §2 에서 ROI 가중합이 Hit@1 을 +3.4%p 올린 것을 보면 이 신호는 살아 있고, 정합성이 개선되면 더 오를 여지가 있다
- **ImageNet 사전학습을 단일 채널 reconstruction error map 에 적용한 것 자체가 근사**다. 흉부 X-ray 도메인 사전학습이 아니고, 입력도 원본 영상이 아니라 error map 이다
- **reconstruction error 가 질환을 변별하지 못할 가능성.** 이상 여부는 잡아도 *어떤* 이상인지는 담지 않을 수 있다. 그렇다면 임베딩을 무엇으로 바꿔도 한계가 같다

다음 실험은 이 셋을 가르는 것이어야 한다. 예컨대 ROI 가중합(`--use-roi`)을 DenseNet 임베딩으로 다시 돌려 §2 의 +3.4%p 가 재현되는지 보면 첫 번째 후보를 시험할 수 있다.

### 8.5 재현

```bash
cd services/xray-rag
export ARANGO_HOST=localhost ARANGO_PORT=8529 ARANGO_USER=root
export XRAY_ARANGO_DATABASE=xray_graph_db PYTHONIOENCODING=utf-8
export ARANGO_PASSWORD="$(grep '^ARANGO_PASSWORD=' ../../infra/.env | cut -d= -f2-)"
python scripts/eval_retrieval.py
```

기준선 대조는 자동 산출물에 없다. 직접 계산한다:

```bash
PW=$(grep '^ARANGO_PASSWORD=' infra/.env | cut -d= -f2-)
curl -s -X POST "http://localhost:8529/_db/xray_graph_db/_api/cursor" -u "root:$PW" \
  -d '{"query":"FOR c IN xray_cases FILTER LENGTH(c.diseaseTags)>0 RETURN c.diseaseTags","batchSize":1000}' \
  -o tags.json
python -c "
import json, collections
rows=json.load(open('tags.json',encoding='utf-8'))['result']
n=len(rows); cnt=collections.Counter(t for r in rows for t in r)
top1=cnt.most_common(1)[0][0]; top3={k for k,_ in cnt.most_common(3)}
print('기준선 top-1:', round(sum(1 for r in rows if top1 in r)/n,4))
print('기준선 top-3:', round(sum(1 for r in rows if top3 & set(r))/n,4))
"
rm -f tags.json
```

**지표를 기록할 때는 항상 이 기준선을 옆에 둔다.** 그것 없이는 0.8014 가 무슨 뜻인지 알 수 없다.
