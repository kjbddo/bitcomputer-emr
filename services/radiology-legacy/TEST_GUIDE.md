# AI_BackEnd API 테스트 가이드

## 테스트 실행 방법

### 1. 서버 시작

터미널 1에서:
```bash
cd c:\Project\BitComputerProject\AI_BackEnd
python start.py
```

또는:
```bash
python app.py
```

서버가 `http://localhost:5000`에서 실행됩니다.

### 2. 테스트 실행

**새 터미널**에서:
```bash
cd c:\Project\BitComputerProject\AI_BackEnd
python test_api.py
```

## 테스트 내용

`test_api.py`는 다음을 테스트합니다:

1. **테스트 이미지 확인**
   - 경로: `Back-End/BitComputer/images/1/original/view1_frontal.jpg`
   - 이미지 파일 존재 여부 확인

2. **헬스 체크 테스트**
   - 엔드포인트: `GET /api/ai/is_running`
   - 서버가 정상적으로 실행 중인지 확인

3. **이상 탐지 API 테스트**
   - 엔드포인트: `POST /api/ai/radiology_report`
   - 이미지 전처리 (256x256 리사이즈, 마스킹 적용)
   - AI 모델 추론
   - 오버레이 이미지 생성
   - 결과 반환

## 예상 출력

```
============================================================
Flask API 테스트 시작
============================================================

============================================================
0. 테스트 이미지 확인
============================================================
이미지 경로: C:\Project\BitComputerProject\Back-End\BitComputer\images\1\original\view1_frontal.jpg
✅ 이미지 파일 존재
   파일 크기: XXX bytes (XXX.XX KB)

============================================================
1. 헬스 체크 테스트
============================================================
상태 코드: 200
응답: {
  "status": "ok",
  "message": "Anomaly Detection API is running"
}
✅ 헬스 체크 성공!

============================================================
2. 이상 탐지 API 테스트
============================================================
요청 데이터:
{
  "radiologyRequestId": 1,
  "patientId": 123,
  "employeeId": 456,
  "deptId": 789,
  "detailImageAddress": "Back-End/BitComputer/images/1/original/view1_frontal.jpg"
}

API 요청 전송 중...
상태 코드: 200

✅ API 호출 성공!

응답 데이터:
{
  "radiologyRequestId": 1,
  "patientId": 123,
  "employeeId": 456,
  "deptId": 789,
  "result": false,
  "summary": "",
  "imageUrl": "Back-End/BitComputer/images/1/overlay/view1_frontal_overlay.jpg",
  "status": ""
}

------------------------------------------------------------
결과 분석:
------------------------------------------------------------
  - Radiology Request ID: 1
  - Patient ID: 123
  - 이상 탐지 결과: 정상 (False)
  - Anomaly Score: false
  - Overlay 이미지 경로: Back-End/BitComputer/images/1/overlay/view1_frontal_overlay.jpg

------------------------------------------------------------
Overlay 이미지 확인:
------------------------------------------------------------
  - 상대 경로: Back-End/BitComputer/images/1/overlay/view1_frontal_overlay.jpg
  - 절대 경로: C:\Project\BitComputerProject\Back-End\BitComputer\images\1\overlay\view1_frontal_overlay.jpg
  - ✅ 파일 존재: ...
  - 파일 크기: XXX bytes (XXX.XX KB)

============================================================
테스트 완료
============================================================
```

## 문제 해결

### 서버가 실행되지 않는 경우
- 포트 5000이 이미 사용 중인지 확인
- 다른 프로세스가 포트를 사용 중이면 종료하거나 포트 변경

### 모델 로딩 오류
- `model/model.pth` 파일이 존재하는지 확인
- `model/discriminator.pth` 파일이 존재하는지 확인
- GPU 메모리가 충분한지 확인

### 이미지 파일을 찾을 수 없는 경우
- 테스트 이미지 경로 확인: `Back-End/BitComputer/images/1/original/view1_frontal.jpg`
- 다른 이미지 파일로 테스트하려면 `test_api.py`의 `TEST_IMAGE_PATH` 수정

### 마스킹 오류
- `utils/CheXmask-Database-main` 폴더가 존재하는지 확인
- `utils/segmentation_processing/hybridgnet_segmenter.py` 파일이 존재하는지 확인
- 마스킹이 실패해도 이미지는 처리되지만, 마스킹 없이 진행됩니다
