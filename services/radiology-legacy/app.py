"""
Flask API 서버 - 이상 탐지 API
eval.py의 test() 함수와 동일한 방식으로 추론 수행
"""
import traceback
import sys
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
import torch
import numpy as np

from config import (
    MODEL_DIR, BITCOMPUTER_ROOT, IMAGES_ROOT,
    HEALTH_CHECK_ENDPOINT, RADIOLOGY_REPORT_ENDPOINT,
    REQUIRED_REQUEST_FIELDS,
    DEFAULT_HOST, DEFAULT_PORT,
    DEFAULT_IMAGE_SIZE, ENABLE_MASKING
)
from model_loader import AnomalyDetector
from image_utils import preprocess_image

# AI tools.py import (squid_exp1_256_mask 폴더에서)
squid_dir = Path(__file__).parent / 'squid_exp1_256_mask'

if squid_dir.exists():
    if str(squid_dir) not in sys.path:
        sys.path.insert(0, str(squid_dir))
    from tools import save_image
else:
    raise ImportError(f"squid_exp1_256_mask 폴더를 찾을 수 없습니다: {squid_dir}")

app = Flask(__name__)
CORS(app)

# 전역 모델 로더
detector: Optional[AnomalyDetector] = None


def init_detector() -> AnomalyDetector:
    """모델 초기화"""
    global detector
    if detector is None:
        detector = AnomalyDetector(MODEL_DIR)
    return detector


def find_image_path(image_address: str) -> Optional[Path]:
    """이미지 경로 찾기"""
    possible_paths = []
    
    if image_address.startswith('images/'):
        possible_paths.extend([
            BITCOMPUTER_ROOT / 'Back-End' / 'BitComputer' / image_address,
            BITCOMPUTER_ROOT / 'Back-End' / image_address,
            BITCOMPUTER_ROOT / image_address,
        ])
    elif image_address.startswith('Back-End/'):
        possible_paths.append(BITCOMPUTER_ROOT / image_address)
        if 'BitComputer' not in image_address:
            possible_paths.append(
                BITCOMPUTER_ROOT / 'Back-End' / 'BitComputer' / image_address.replace('Back-End/', '')
            )
    else:
        possible_paths.extend([
            BITCOMPUTER_ROOT / image_address,
            BITCOMPUTER_ROOT / 'Back-End' / image_address,
            BITCOMPUTER_ROOT / 'Back-End' / 'BitComputer' / image_address,
        ])
    
    for path in possible_paths:
        if path.exists():
            return path
    return None


def extract_folder_id(image_address: str) -> str:
    """이미지 경로에서 folder_id 추출"""
    parts = Path(image_address).parts
    if 'images' in parts:
        idx = parts.index('images')
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return '1'


@app.route(HEALTH_CHECK_ENDPOINT, methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({
        'status': 'ok',
        'message': 'Anomaly Detection API is running'
    })


@app.route(RADIOLOGY_REPORT_ENDPOINT, methods=['POST'])
def detect_anomaly():
    """이상 탐지 API - eval.py의 test() 함수와 동일한 방식"""
    try:
        # 요청 데이터 파싱
        data = request.get_json()
        
        if not data:
            return jsonify({'error': '요청 데이터가 없습니다.'}), 400
        
        # 필수 필드 확인
        missing_fields = [field for field in REQUIRED_REQUEST_FIELDS if field not in data]
        if missing_fields:
            return jsonify({'error': f'필수 필드가 없습니다: {missing_fields}'}), 400
        
        # 이미지 경로 찾기
        image_address = data['detailImageAddress']
        image_path = find_image_path(image_address)
        
        if image_path is None:
            return jsonify({'error': f'이미지 파일을 찾을 수 없습니다: {image_address}'}), 404
        
        # folder_id 추출
        folder_id = extract_folder_id(image_address) or str(data['radiologyRequestId'])
        
        # 모델 초기화
        detector = init_detector()
        
        # 마스크 경로 생성
        mask_path = None
        if ENABLE_MASKING:
            mask_dir = IMAGES_ROOT / folder_id / 'mask'
            mask_dir.mkdir(parents=True, exist_ok=True)
            mask_path = mask_dir / f'{image_path.stem}.npy'
        
        # 이미지 전처리 (모델 입력용)
        img_tensor, mask_tensor = preprocess_image(image_path, mask_path)
        
        # eval.py의 test() 함수와 동일한 방식으로 추론 수행
        detector.model.eval()
        detector.discriminator.eval()
        
        img_tensor = img_tensor.to(detector.device)
        if mask_tensor is not None:
            mask_tensor = mask_tensor.to(detector.device)
        
        with torch.no_grad():
            out = detector.model(img_tensor)
            
            # ===== ROI 마스킹: 폐와 심장 영역만 discriminator에 입력 =====
            if mask_tensor is not None:
                if mask_tensor.shape[1] == 1 and out['recon'].shape[1] > 1:
                    mask_expanded = mask_tensor.expand_as(out['recon'])
                else:
                    mask_expanded = mask_tensor
                fake_recon_masked = out['recon'] * mask_expanded
            else:
                fake_recon_masked = out['recon']
            fake_v = detector.discriminator(fake_recon_masked)
            raw_score = float(fake_v.detach().cpu().numpy()[0])  # discriminator의 raw 출력값
        
        # ===== 이상 탐지 로직 (AI 코드와 동일) =====
        # 1. Score 정규화: train_loader에서 계산된 mean/std 사용
        #    - mean/std는 평가 시 train_loader에서 동적으로 계산된 값
        #    - 평가 결과(model_config.txt)에서 로드하거나 기본값 사용
        # 2. 확률 변환: sigmoid 함수를 사용하여 0-1 범위로 변환
        #    - expit(x) = 1 / (1 + exp(-x)) = sigmoid(x)
        #    - 1.0 - expit(score_normalized): 1이 anomaly, 0이 normal
        # 3. Threshold 비교: 확률 변환된 값과 threshold 비교
        #    - threshold는 평가 시 최적 정확도로 계산된 값
        #    - score_prob >= threshold이면 anomaly로 판정
        from scipy.special import expit
        score_normalized = (raw_score - detector.mean) / (detector.std + 1e-8)
        score_prob = float(1.0 - expit(score_normalized))  # 1이 anomaly, 0이 normal (확률 값)
        
        # 이상 여부 판정
        is_anomaly = bool(score_prob >= detector.threshold)  # threshold는 확률 변환 후 값에 대한 threshold
        
        # ===== 히트맵/오버레이용: 원본 이미지와 재구성 이미지 저장 (마스크는 별도 저장) =====
        # AI 코드는 normalize=False이므로 정규화하지 않음
        # 모델 입력/출력은 이미 0-1 범위이므로 역정규화 불필요
        recon_np = out['recon'].detach().cpu().numpy()  # [B, C, H, W] - 0-1 범위
        img_np = img_tensor.detach().cpu().numpy()  # [B, C, H, W] - 0-1 범위
        
        # 0-1 범위로 클리핑 (안전장치)
        recon_np = np.clip(recon_np, 0, 1)
        img_np = np.clip(img_np, 0, 1)
        
        # 배치를 개별 이미지로 분리하여 저장
        reconstructed_np = recon_np[0]  # [C, H, W]
        input_np = img_np[0]  # [C, H, W]
        
        # 마스크 저장 (히트맵 생성 시 사용)
        if mask_tensor is not None:
            mask_np = mask_tensor.detach().cpu().numpy()  # [B, 1, H, W]
            mask_for_save = mask_np[0]  # [1, H, W]
        else:
            # 마스크가 없으면 전체 영역 마스크 (모든 픽셀 1)
            mask_for_save = np.ones((1, img_np.shape[2], img_np.shape[3]), dtype=np.float32)
        
        overlay_dir = IMAGES_ROOT / folder_id / 'overlay'
        overlay_dir.mkdir(parents=True, exist_ok=True)
        data_list = [(reconstructed_np, input_np, mask_for_save)]
        save_image(str(overlay_dir), data_list, save_heatmaps=True)
        
        # 파일명 변경 (overlay_000.jpg -> {filename}_overlay.jpg)
        overlay_old = overlay_dir / 'overlay_000.jpg'
        overlay_new = overlay_dir / f'{image_path.stem}_overlay.jpg'
        if overlay_old.exists():
            overlay_old.rename(overlay_new)
        
        # 상대 경로 생성
        overlay_url = str(overlay_new.relative_to(BITCOMPUTER_ROOT)).replace('\\', '/')
        
        # 응답 생성 (req/res 형태 유지)
        response = {
            'radiologyRequestId': data['radiologyRequestId'],
            'patientId': data['patientId'],
            'employeeId': data['employeeId'],
            'deptId': data['deptId'],
            'result': is_anomaly,
            'summary': '',
            'imageUrl': overlay_url,
            'status': ''
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        error_msg = f'서버 오류가 발생했습니다: {str(e)}'
        print(f"[ERROR] {error_msg}")
        traceback.print_exc()
        return jsonify({
            'error': error_msg,
            'errorType': type(e).__name__
        }), 500


if __name__ == '__main__':
    print("Flask 서버를 시작합니다...")
    print(f"프로젝트 루트: {BITCOMPUTER_ROOT}")
    print(f"이미지 루트: {IMAGES_ROOT}")
    print(f"모델 경로: {MODEL_DIR}")
    app.run(host=DEFAULT_HOST, port=DEFAULT_PORT, debug=True)
