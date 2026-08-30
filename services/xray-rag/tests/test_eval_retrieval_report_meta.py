"""eval_retrieval.py 의 리포트 메타데이터가 embedding_version 을 어디서 읽는지 검증한다.

7bf1439 은 `Settings.EMBEDDING_VERSION` 기본값("mock_pca_v1")을 의도적으로 없앴다.
설정 기본값이 실제로 돌아간 모델과 무관하게 모든 리포트에 그대로 찍히는 문제를
고치기 위해서였다(app/ml/factory.py 의 `BuildResult.embedding_version`, 그리고
tests/test_embedding_version.py 참조). 값의 유일한 출처는 실제로 구성된 인코더다.

그런데 scripts/eval_retrieval.py 는 여전히 `settings.EMBEDDING_VERSION` 을 그대로
읽어 리포트 메타에 박는다. 기본값이 없어진 지금 이 줄은 항상 None 을 기록한다 —
이 eval 리포트는 몇 달 뒤 "이 숫자를 만든 인코더가 무엇이었나"를 답해야 하는
유일한 기록인데, null 이면 그 질문에 답할 수 없다. 리포트도 case_service 와
서비스 컨테이너가 이미 쓰는 것과 같은 소스(`container.embedding_version`, 즉
`BuildResult.embedding_version`)를 읽어야 한다.
"""
from scripts.eval_retrieval import _build_meta


class _FakeSettingsWithDefaultRemoved:
    """7bf1439 이후의 실제 상태 — EMBEDDING_VERSION 기본값이 없다."""

    MODEL_VERSION = "squid_v1"
    EMBEDDING_VERSION = None
    EMBEDDING_DIM = 1024


def test_meta_uses_container_embedding_version_not_none_setting():
    """settings.EMBEDDING_VERSION 이 None(현재 실제 상태)이어도, 실제로 구성된
    모델의 버전이 리포트에 찍혀야 한다 — None 이 찍히면 안 된다."""
    meta = _build_meta(
        settings=_FakeSettingsWithDefaultRemoved(),
        embedding_version="densenet121_imagenet_1024",
        weights={"global": 1.0},
        view=None,
    )

    assert meta["embedding_version"] == "densenet121_imagenet_1024"


def test_meta_does_not_fall_back_to_settings_embedding_version():
    """회귀 방지: settings.EMBEDDING_VERSION 을 다시 읽는 방향으로 되돌아가면
    이 테스트가 빨개진다 — settings 쪽에 다른 값을 심어 대조한다."""
    class _FakeSettingsWithStaleValue:
        MODEL_VERSION = "squid_v1"
        EMBEDDING_VERSION = "SHOULD_NOT_BE_USED"
        EMBEDDING_DIM = 1024

    meta = _build_meta(
        settings=_FakeSettingsWithStaleValue(),
        embedding_version="real_model_version",
        weights={},
        view="AP",
    )

    assert meta["embedding_version"] == "real_model_version"
    assert meta["embedding_version"] != "SHOULD_NOT_BE_USED"


def test_meta_still_carries_other_settings_fields():
    """model_version·embedding_dim·view_filter 는 이번 변경과 무관하게 그대로여야
    한다 — embedding_version 출처만 바뀌는 것이지 다른 필드까지 깨지면 안 된다."""
    meta = _build_meta(
        settings=_FakeSettingsWithDefaultRemoved(),
        embedding_version="densenet121_imagenet_1024",
        weights={"global": 0.5, "right_lung": 0.5},
        view="AP",
    )

    assert meta["model_version"] == "squid_v1"
    assert meta["embedding_dim"] == 1024
    assert meta["view_filter"] == "AP"


class _FakeAql:
    def __init__(self, cases):
        self._cases = cases

    def execute(self, _query, bind_vars=None):
        return iter(self._cases)


class _FakeDb:
    def __init__(self, cases):
        self.aql = _FakeAql(cases)


class _FakeContainer:
    """실제 ServiceContainer 대역. embedding_version 은 settings 와 일부러
    다른 값으로 둬 두 출처를 구분한다."""

    def __init__(self, cases, embedding_version):
        self.db = _FakeDb(cases)
        self.embedding_version = embedding_version


def test_main_writes_container_embedding_version_into_report(tmp_path, monkeypatch):
    """main() 전체를 실제로 돌려, 기록되는 metrics.json 이 container.embedding_version
    을 쓰는지 확인한다 — _build_meta 단위 테스트만으로는 main() 이 그 함수에 어떤
    값을 넘기는지 보장하지 못한다. settings.EMBEDDING_VERSION 을 다시 읽는 방향으로
    호출부가 되돌아가면(§7bf1439 이전 상태) 이 테스트가 빨개진다."""
    import json as _json

    import scripts.eval_retrieval as eval_retrieval

    cases = [
        {
            "_key": "case1",
            "diseaseTags": ["Effusion"],
            "view": "AP",
            "modelVersion": "v1",
            "globalErrorEmbedding": [0.1, 0.2, 0.3, 0.4],
        },
        {
            "_key": "case2",
            "diseaseTags": ["Effusion"],
            "view": "AP",
            "modelVersion": "v1",
            "globalErrorEmbedding": [0.4, 0.3, 0.2, 0.1],
        },
    ]

    class _FakeSettings:
        MODEL_VERSION = "squid_v1"
        EMBEDDING_VERSION = "STALE_SETTING_SHOULD_NOT_APPEAR"
        EMBEDDING_DIM = 4
        ARANGO_URL = "bolt://fake"
        ARANGO_DB_NAME = "fake_db"
        STORAGE_DIR = tmp_path

    fake_settings = _FakeSettings()
    fake_container = _FakeContainer(cases, embedding_version="densenet121_imagenet_1024")

    monkeypatch.setattr(eval_retrieval, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(eval_retrieval, "get_container", lambda: fake_container)
    monkeypatch.setattr(
        "sys.argv", ["eval_retrieval.py", "--out", str(tmp_path / "out")]
    )

    rc = eval_retrieval.main()
    assert rc == 0

    written = _json.loads((tmp_path / "out" / "metrics.json").read_text(encoding="utf-8"))
    assert written["meta"]["embedding_version"] == "densenet121_imagenet_1024"
    assert written["meta"]["embedding_version"] != "STALE_SETTING_SHOULD_NOT_APPEAR"
