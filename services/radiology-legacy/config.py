"""
AI_BackEnd 설정 파일
"""
import os
from pathlib import Path

# 프로젝트 루트 경로
BITCOMPUTER_ROOT = Path(__file__).parent.parent.resolve()

# 모델 디렉토리 (squid_exp1_256_mask 폴더 사용).
# 가중치는 저장소에 커밋하지 않고 scripts/fetch-models.sh 로 내려받으므로,
# 환경변수 SQUID_MODEL_DIR 로 재정의할 수 있게 하되 기본값은 기존 경로를 유지한다.
MODEL_DIR = Path(os.environ.get(
    "SQUID_MODEL_DIR",
    str(Path(__file__).resolve().parent / 'squid_exp1_256_mask'),
))

# 이미지 루트 경로
IMAGES_ROOT = BITCOMPUTER_ROOT / 'Back-End' / 'BitComputer' / 'images'

# API 엔드포인트
HEALTH_CHECK_ENDPOINT = '/api/ai/is_running'
RADIOLOGY_REPORT_ENDPOINT = '/api/ai/radiology_report'

# 필수 요청 필드
REQUIRED_REQUEST_FIELDS = [
    'radiologyRequestId',
    'patientId',
    'employeeId',
    'deptId',
    'detailImageAddress'
]

# 서버 설정
DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 5000

# 이미지 설정
DEFAULT_IMAGE_SIZE = 256
DEFAULT_MEAN = 0.1307
DEFAULT_STD = 0.3081
ENABLE_MASKING = True

# 이상 탐지 설정
DEFAULT_THRESHOLD = 0.85
