# 이상 탐지 API 서버

Spring Boot 백엔드와 통신하는 Flask 기반 이상 탐지 API 서버입니다.

## 시작 전 준비

### 모델 파일 다운로드

pth 파일 필요:
- https://drive.google.com/file/d/1V_8ZZOgAp9hn_6l_wmV3hzkblpy5FeV4/view?usp=sharing
- https://drive.google.com/file/d/1_MfbGySEBEH2RLO0RAtVwYMFWjizJyDF/view?usp=sharing

`discriminator.pth`, `model.pth` 파일을 다운받아 `squid_exp1_256_mask/` 폴더에 배치합니다.

## 기능

- X-ray 이미지 이상 탐지
- Overlay 이미지 생성 (히트맵 포함)
- RESTful API 제공
- 자동 threshold 및 mean/std 로드

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
python app.py
```

서버는 `http://localhost:5000`에서 실행됩니다.

## 테스트

서버를 실행한 후, 다른 터미널에서 테스트 스크립트를 실행할 수 있습니다:

```bash
python test_api.py
```

테스트 스크립트는:
- 헬스 체크 엔드포인트 테스트
- `images/1/original/view1_frontal.jpg` 이미지를 사용한 이상 탐지 API 테스트
- 생성된 overlay 이미지 파일 확인

## API 엔드포인트

### 1. 헬스 체크 (`/api/ai/is_running`)

**용도**: 서버가 정상적으로 동작하는지 간단히 확인하는 엔드포인트
- 모델 로드 없이 빠르게 응답
- 서버 상태 모니터링 및 로드밸런서 체크에 사용

```
GET /api/ai/is_running
```

**응답:**
```json
{
  "status": "ok",
  "message": "Anomaly Detection API is running"
}
```

### 2. 이상 탐지 (`/api/ai/radiology_report`)

**용도**: X-ray 이미지를 분석하여 이상 탐지를 수행하는 메인 엔드포인트
- AI 모델을 사용하여 이미지 분석
- Overlay 이미지 생성 (히트맵 포함)
- 분석 결과 반환

```
POST /api/ai/radiology_report
Content-Type: application/json
```

**요청 본문:**

```json
{
  "radiologyRequestId": 1,
  "patientId": 123,
  "employeeId": 456,
  "deptId": 789,
  "symptomDetail": "증상 상세",
  "memo": "메모",
  "entryDate": "2024-01-01",
  "detailImageAddress": "images/1/original/view1_frontal.jpg"
}
```

**응답:**

```json
{
  "radiologyRequestId": 1,
  "patientId": 123,
  "employeeId": 456,
  "deptId": 789,
  "result": true,
  "summary": "",
  "imageUrl": "images/1/overlay/view1_frontal_overlay.jpg",
  "status": ""
}
```

- `result`: `true` = 질병 의심 (anomaly), `false` = 이상 없음 (normal)
- `imageUrl`: 생성된 overlay 이미지의 상대 경로

## 구조

```
AI_BackEnd/
├── app.py                      # Flask 애플리케이션 (메인 서버)
├── config.py                   # 설정 파일 (경로, 엔드포인트 등)
├── model_loader.py             # 모델 로드 및 추론 클래스
├── image_utils.py              # 이미지 전처리/후처리 유틸리티
├── threshold_loader.py         # 평가 결과(threshold, mean/std) 로드 유틸리티
├── configs/                    # 모델 설정 파일들
│   ├── base.py
│   └── chexpert_best.py
├── dataloader/                 # 데이터 로더
│   └── dataloader_chexpert.py
├── models/                     # 모델 서브모듈
│   ├── __init__.py
│   ├── basic_modules.py
│   ├── memory.py
│   ├── inpaint.py
│   ├── squid.py
│   └── discriminator.py
├── squid_exp1_256_mask/        # 모델 체크포인트 폴더
│   ├── model.pth              # SQUID 모델 체크포인트
│   ├── discriminator.pth      # Discriminator 체크포인트
│   ├── config.py               # 모델 설정 파일
│   ├── squid.py                # SQUID 모델 코드
│   ├── discriminator.py        # Discriminator 모델 코드
│   ├── tools.py                # 유틸리티 함수 (이미지 저장 등)
│   └── visualizations/         # 평가 결과 폴더
│       └── YYYYMMDD_HHMMSS/    # 평가 날짜별 폴더
│           ├── model_config.txt    # 평가 결과 (threshold, mean/std 포함)
│           ├── confusion_matrix.png
│           ├── roc_curve.png
│           ├── pr_curve.png
│           └── score_distribution.png
├── utils/                      # 유틸리티
│   ├── segmentation_processing/    # 마스킹 처리
│   │   └── hybridgnet_segmenter.py
│   └── CheXmask-Database-main/     # 마스킹 모델
├── requirements.txt            # 의존성 패키지
├── test_api.py                 # API 테스트 스크립트
└── README.md                   # 이 파일
```

## 필요한 파일 목록

### 필수 파일 (반드시 있어야 함)

모델 파일들은 `squid_exp1_256_mask/` 폴더에 있어야 합니다:

1. **`model.pth`** - SQUID 모델 체크포인트 파일
2. **`discriminator.pth`** - Discriminator 모델 체크포인트 파일
3. **`config.py`** - 모델 설정 파일 (하이퍼파라미터 포함)
4. **`squid.py`** - SQUID 모델 코드 (AE 클래스)
5. **`discriminator.py`** - Discriminator 모델 코드
6. **`tools.py`** - 유틸리티 함수 (이미지 저장 등)

### 평가 결과 파일 (자동 로드)

`visualizations/` 폴더의 가장 최근 평가 결과에서 다음 값들을 자동으로 로드합니다:

1. **`threshold`** - 이상 탐지 임계값 (최적 정확도로 계산된 값)
2. **`Score Normalization Mean`** - Score 정규화 평균값
3. **`Score Normalization Std`** - Score 정규화 표준편차

평가 결과 파일(`model_config.txt`)이 없으면 기본값을 사용합니다:
- 기본 threshold: `0.85`
- 기본 mean: `0.1307`
- 기본 std: `0.3081`

⚠️ **주의**: 기본값은 실제 평가 시 사용된 값과 다를 수 있으므로 정확도에 영향을 줄 수 있습니다.

## 이상 탐지 로직

이상 탐지는 다음과 같은 프로세스로 수행됩니다:

1. **이미지 전처리**
   - 이미지를 256x256 크기로 리사이즈
   - 그레이스케일 변환
   - 텐서 변환 (정규화 없음, 0-1 범위 유지)

2. **모델 추론**
   - SQUID 모델로 재구성 이미지 생성
   - ROI 마스킹 (폐와 심장 영역만 사용, 선택적)
   - Discriminator로 raw score 계산

3. **Score 정규화 및 확률 변환**
   ```
   raw_score (discriminator 출력)
   ↓
   score_normalized = (raw_score - mean) / std
   ↓
   score_prob = 1.0 - expit(score_normalized)  # 0-1 범위, 1이 anomaly
   ```

4. **이상 여부 판정**
   ```
   is_anomaly = score_prob >= threshold
   ```
   - `threshold`는 평가 시 최적 정확도로 계산된 값
   - `mean/std`는 평가 시 train_loader에서 계산된 값
   - 동일한 `mean/std`를 사용해야 `threshold`가 올바르게 적용됨

5. **재구성 이미지 저장**
   - 재구성 이미지와 원본 이미지를 0-1 범위로 저장
   - 히트맵 생성 (재구성 오차 시각화)
   - Overlay 이미지 생성 (원본 + 히트맵)

## 배포 시 주의사항

- **AI 폴더가 없는 환경**에서도 동작하도록 설계되었습니다.
- 평가 결과 파일(`model_config.txt`)은 `visualizations/YYYYMMDD_HHMMSS/` 폴더에 자동으로 생성됩니다.
- 가장 최근 평가 결과의 `threshold`와 `mean/std`를 자동으로 로드합니다.
- 이미지 경로는 `Back-End/BitComputer/images/{id}/original/` 구조를 따릅니다.
- 생성된 overlay 이미지는 `Back-End/BitComputer/images/{id}/overlay/` 폴더에 저장됩니다.
- 마스크 파일은 `Back-End/BitComputer/images/{id}/mask/` 폴더에 저장됩니다 (캐싱).

## 설정

`config.py`에서 다음 설정을 변경할 수 있습니다:

- `MODEL_DIR`: 모델 디렉토리 경로
- `IMAGES_ROOT`: 이미지 루트 경로
- `DEFAULT_IMAGE_SIZE`: 이미지 크기 (기본값: 256)
- `ENABLE_MASKING`: 마스킹 기능 활성화 여부 (기본값: True)
- `DEFAULT_THRESHOLD`: 기본 threshold (평가 결과가 없을 때 사용)
- `DEFAULT_MEAN`: 기본 mean (평가 결과가 없을 때 사용)
- `DEFAULT_STD`: 기본 std (평가 결과가 없을 때 사용)

## 문제 해결

### 모델 로드 실패
- `squid_exp1_256_mask/` 폴더에 필요한 파일들이 모두 있는지 확인
- `model.pth`, `discriminator.pth` 파일이 올바른 위치에 있는지 확인

### Threshold/Mean/Std 로드 실패
- `visualizations/` 폴더에 평가 결과가 있는지 확인
- `model_config.txt` 파일에 `threshold`, `Score Normalization Mean`, `Score Normalization Std`가 포함되어 있는지 확인
- 없으면 기본값을 사용하지만 정확도에 영향을 줄 수 있습니다

### 이미지 저장 실패
- `Back-End/BitComputer/images/` 폴더에 쓰기 권한이 있는지 확인
- 디스크 공간이 충분한지 확인
