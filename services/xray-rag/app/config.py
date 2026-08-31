"""
전역 설정. 환경 변수에서 읽되, 모든 키에 합리적인 기본값을 둔다.

설계 메모:
- 본 시스템은 분류 모델을 쓰지 않고 reconstruction error embedding으로 case retrieval을 한다.
- mock-first: 환경에 모델 파일이 없어도 end-to-end 동작을 보장한다.
- 실제 PyTorch 모델 연결은 USE_TORCH_ANOMALY=true 등으로 토글한다.
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional


def _find_project_root(start: Path) -> Path:
    """모노레포 루트를 표시하는 마커(형제 `services/`, `apps/` 디렉터리)를 찾을 때까지
    상위 디렉터리로 올라간다.

    호스트에서는 이 파일이 `services/xray-rag/app/config.py` 에 있으므로 고정된
    `parents[N]` 인덱스로도 루트를 찾을 수 있었지만, Dockerfile 은 `app/`, `scripts/`
    만 `/app/app`, `/app/scripts` 로 골라서 복사하고 `xray-rag` 상위 디렉터리 계층은
    복사하지 않는다. 그 결과 컨테이너 안에서는 이 파일이 `/app/app/config.py` 에
    있게 되어, 호스트 기준으로 계산한 고정 인덱스(`parents[3]`)가 존재하지 않는
    상위 디렉터리를 가리키며 `IndexError` 로 임포트 시점에 죽었다.

    고정 인덱스 대신 마커 디렉터리를 찾을 때까지 걸어 올라가면 호스트에서는
    기존과 동일하게 리포지토리 루트를 찾고, 컨테이너처럼 마커가 없는 레이아웃에서는
    파일시스템 루트에 도달한 시점에 멈춰 폴백값을 반환한다 — 여기서 계산되는
    PROJECT_ROOT 는 STORAGE_DIR/SQUID_MODEL_DIR 의 "기본값"을 만드는 데만 쓰이고,
    컨테이너에서는 두 값 모두 환경변수로 직접 주입되므로 폴백값이 틀려도
    실제로 사용되지 않는다. 중요한 건 임포트 시점에 죽지 않는 것이다.
    """
    current = start.parent
    while True:
        if (current / "services").is_dir() and (current / "apps").is_dir():
            return current
        if current.parent == current:
            # 마커를 찾지 못함(예: 컨테이너 레이아웃) — 파일시스템 루트에서 멈춘다.
            return current
        current = current.parent


_PROJECT_ROOT = _find_project_root(Path(__file__).resolve())

# 프로젝트 루트의 .env 를 가능한 한 빨리 로드한다.
# - OS 환경변수가 이미 설정돼 있으면 그쪽이 우선 (override=False).
#   → Docker compose 가 ARANGO_PASSWORD 등을 직접 주입한 컨테이너 환경에서는
#     컨테이너 환경변수가 그대로 유지된다.
# - python-dotenv 가 미설치된 환경(예: 최소 의존만 설치된 컨테이너)에서도
#   ImportError 로 죽지 않도록 안전하게 무시한다.
try:
    from dotenv import load_dotenv  # type: ignore

    for _candidate in (_PROJECT_ROOT / ".env", _PROJECT_ROOT / "services" / "xray-rag" / ".env"):
        if _candidate.exists():
            load_dotenv(_candidate, override=False)
            break
except Exception:
    pass


def _bool(v: Optional[str], default: bool) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _int(v: Optional[str], default: int) -> int:
    try:
        return int(v) if v is not None else default
    except ValueError:
        return default


def _float(v: Optional[str], default: float) -> float:
    try:
        return float(v) if v is not None else default
    except ValueError:
        return default


class Settings:
    PROJECT_ROOT: Path = _PROJECT_ROOT
    APP_ROOT: Path = Path(__file__).resolve().parent

    # ArangoDB
    ARANGO_URL: str = os.environ.get("ARANGO_URL", "http://localhost:8529")
    ARANGO_DB_NAME: str = os.environ.get("ARANGO_DB_NAME", "xray_graph_db")
    ARANGO_USERNAME: str = os.environ.get("ARANGO_USERNAME", "root")
    ARANGO_PASSWORD: str = os.environ.get("ARANGO_PASSWORD", "")
    ARANGO_GRAPH_NAME: str = os.environ.get("ARANGO_GRAPH_NAME", "xray_graph")

    # Vector index. ArangoDB 3.12+에서 vector type 인덱스 지원.
    # 기본값 1024는 app.ml.torch_embedding_model 의 DenseNet121(ImageNet 사전학습)
    # backbone이 만드는 pooled feature의 네이티브 차원과 맞춘 것이다(투영 없이
    # 그대로 저장). xray_cases 컬렉션이 비어 있는 동안 이 기본값을 바꿨다 -
    # 데이터가 쌓인 뒤 바꾸면 기존 벡터 인덱스와 차원이 어긋난다.
    EMBEDDING_DIM: int = _int(os.environ.get("EMBEDDING_DIM"), 1024)
    VECTOR_METRIC: str = os.environ.get("VECTOR_METRIC", "cosine")
    VECTOR_NLISTS: int = _int(os.environ.get("VECTOR_NLISTS"), 100)
    VECTOR_NPROBE: int = _int(os.environ.get("VECTOR_NPROBE"), 20)
    VECTOR_TRAINING_ITERS: int = _int(os.environ.get("VECTOR_TRAINING_ITERS"), 25)

    # Storage
    STORAGE_DIR: Path = Path(os.environ.get("STORAGE_DIR", str(PROJECT_ROOT / "services" / "xray-rag" / "storage")))

    # Image processing
    IMAGE_SIZE: int = _int(os.environ.get("IMAGE_SIZE"), 256)

    # Model versioning(같은 modelVersion / maskVersion끼리만 비교하도록 필터에 사용)
    MODEL_VERSION: str = os.environ.get("MODEL_VERSION", "ae_squid_v1")
    MASK_VERSION: str = os.environ.get("MASK_VERSION", "lung_heart_mask_v1")
    # 기본값을 두지 않는다. 값이 있으면 embeddingVersion 을 그것으로 고정하지만,
    # 비어 있으면 실제로 구성된 임베딩 모델이 스스로 답한다
    # (factory.BuildResult.embedding_version). 예전 기본값 "mock_pca_v1" 은
    # DenseNet 벡터에도 그대로 박혀, 저장된 벡터의 출처를 알 수 없게 만들었다.
    EMBEDDING_VERSION: Optional[str] = os.environ.get("EMBEDDING_VERSION") or None

    # ML toggles
    USE_TORCH_ANOMALY: bool = _bool(os.environ.get("USE_TORCH_ANOMALY"), False)
    USE_TORCH_EMBEDDING: bool = _bool(os.environ.get("USE_TORCH_EMBEDDING"), False)
    # 영상 적응형 ROI 분할(app.ml.cv_roi_model). 외부 가중치가 필요 없고 numpy/scipy
    # 만 쓰므로 기본값이 true 다 - USE_TORCH_* 와 달리 "받아와야 하는 파일"이 없다.
    # false 로 두면 예전 고정 타원(MockROIModel)으로 돌아간다.
    # 예전 USE_TORCH_ROI 는 읽는 곳이 없는 no-op 이었다
    # (Docs/superpowers/specs/2026-08-26-phase-a-foundation-design.md 미결 항목 9번). 실
    # 어댑터가 생긴 지금 그 이름을 살려두면 "torch ROI 모델이 있다"는 잘못된 신호가
    # 되므로 지운다. 학습된 ROI 모델을 붙이는 날 별도 토글을 새로 만든다.
    USE_CV_ROI: bool = _bool(os.environ.get("USE_CV_ROI"), True)
    # 사전학습 해부학 분할(ChestX-Det PSPNet, app.ml.pspnet_roi_model). ROI 어댑터
    # 우선순위는 pspnet > cv > mock 이고, 이 토글은 그 첫 번째를 "시도하라"는
    # 뜻일 뿐이다 - 실제로 올라왔는지는 factory.BuildResult.roi_status 가 답한다.
    #
    # **기본값은 False 다. docker-compose.yml / .env.example 과 같아야 한다.**
    #
    # 예전에는 여기만 True 였다. 그 결과: 컨테이너는 compose 기본값(false)으로
    # cv 마스크로 질의하는데, **호스트에서 도는 적재 스크립트는 이 기본값을 읽어
    # pspnet 으로 코퍼스를 만들었다.** 저장과 질의가 서로 다른 해부 기준 위에
    # 놓이는데 양쪽 다 정상으로 보인다 - 런북대로 따라가기만 해도 그 상태가
    # 만들어졌다.
    #
    # 기본값을 끄는 이유는 성능이다. CPU 에서 분할 한 번에 18~32초라 적재가
    # 세 배 가까이 길어지는데(202건 기준 6분 -> 15분), EVALUATION.md 11.3 에서
    # 다수 라벨 기준선을 넘지 못했다. GPU 가 붙으면 그때 켠다.
    USE_PSPNET_ROI: bool = _bool(os.environ.get("USE_PSPNET_ROI"), False)
    # 가중치(273MB) 캐시 디렉터리. 비우면 torchxrayvision 기본값
    # (~/.torchxrayvision/models_data/)을 쓴다. 컨테이너는 호스트 캐시를
    # 마운트한 경로를 여기로 준다.
    PSPNET_CACHE_DIR: Optional[str] = os.environ.get("PSPNET_CACHE_DIR") or None
    # 가중치가 없을 때 런타임 다운로드를 허용할지. **기본은 false 다.** 운영
    # 컨테이너에는 egress 가 없어서, 허용해두면 기동이 네트워크 타임아웃만큼
    # 멈춘다. 호스트에서 한 번 받아두는 것은
    # scripts/fetch_pspnet_weights.py 가 한다.
    PSPNET_ALLOW_DOWNLOAD: bool = _bool(os.environ.get("PSPNET_ALLOW_DOWNLOAD"), False)

    # SQUID 모델 폴더. 가중치는 scripts/fetch-models.sh 로 내려받는다.
    # 주의: services/radiology-legacy/ 의 직계 자식이어야 한다. torch_anomaly_model.py 가
    # `model_dir.parent` 를 AI_BackEnd 루트(config.py/model_loader.py가 있는 위치)로 간주해
    # 거기서 `config.py` 를 강제로 로드하기 때문에, 중간에 `models/` 같은 계층을 끼우면
    # `AI_BackEnd/config.py not found` 로 즉시 깨진다.
    SQUID_MODEL_DIR: Path = Path(
        os.environ.get(
            "SQUID_MODEL_DIR",
            str(PROJECT_ROOT / "services" / "radiology-legacy" / "squid_exp1_256_mask"),
        )
    )

    # Retrieval
    DEFAULT_TOP_K: int = _int(os.environ.get("DEFAULT_TOP_K"), 20)

    # Severity thresholds (p95 기준)
    SEVERITY_HIGH_P95: float = _float(os.environ.get("SEVERITY_HIGH_P95"), 0.25)
    SEVERITY_HIGH_AREA: float = _float(os.environ.get("SEVERITY_HIGH_AREA"), 0.20)
    SEVERITY_MEDIUM_P95: float = _float(os.environ.get("SEVERITY_MEDIUM_P95"), 0.12)

    # Uncertainty thresholds
    UNCERT_HIGH_TOP1: float = _float(os.environ.get("UNCERT_HIGH_TOP1"), 0.65)
    UNCERT_MED_GAP: float = _float(os.environ.get("UNCERT_MED_GAP"), 0.10)
    UNCERT_MIN_CASES: int = _int(os.environ.get("UNCERT_MIN_CASES"), 8)

    # Safety文구
    SAFETY_NOTICE: str = (
        "이 결과는 의학적 진단이 아닙니다. "
        "유사 reconstruction error pattern 기반의 후보 추론이며, "
        "최종 판독 및 진단은 반드시 영상의학 전문의가 수행해야 합니다."
    )

    @property
    def images_dir(self) -> Path:
        return self.STORAGE_DIR / "images"

    @property
    def recon_dir(self) -> Path:
        return self.STORAGE_DIR / "recon"

    @property
    def heatmap_dir(self) -> Path:
        return self.STORAGE_DIR / "heatmaps"

    def ensure_storage(self) -> None:
        for p in (self.images_dir, self.recon_dir, self.heatmap_dir):
            p.mkdir(parents=True, exist_ok=True)

    # engineStatus 판정은 여기서 하지 않는다. USE_TORCH_* 는 "시도" 토글일 뿐,
    # 실제로 torch 어댑터가 구성됐는지는 app.ml.factory.build_models() 의 결과로만
    # 알 수 있다(가중치 누락 등으로 로드가 실패하면 토글이 true여도 mock으로
    # fallback 한다). 판정 로직은 app.ml.factory.BuildResult.engine_status 를,
    # 그 값의 보관/사용은 app.api.dependencies.ServiceContainer 와
    # app.services.case_service.CaseService 를 참고.


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_storage()
    return s
