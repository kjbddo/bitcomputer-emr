"""같은 원본을 다시 적재해도 코퍼스가 복제되지 않아야 한다.

`scripts/seed_chexpert.py` 는 실행할 때마다 케이스 키를 `secrets.token_hex` 로
새로 만들었다. 그래서 같은 CheXpert split 을 두 번 돌리면 같은 영상이 두 개의
서로 다른 케이스가 됐다.

이게 조용했던 이유가 있다. 등록할 때마다 원본 이미지를 케이스 키로 된 **새
경로에 복사**하므로, `imagePath` 로 묶어 세면 중복이 0으로 나온다. 실제로
202장짜리 valid split 이 573건이 될 때까지 아무 지표도 이상해 보이지 않았고,
그중 202건은 다른 ROI 마스크 기준으로 만들어져 있어서 유사도 검색이 서로 다른
해부 구조끼리를 비교하고 있었다.

여기서 고정하는 것은 셋이다.

1. 같은 원본은 같은 키를 받는다 — 재실행이 덮어쓰기가 된다
2. 덮어쓸 때 **없어진 태그의 간선이 남지 않는다** — 키가 case_key 에서
   유도되므로 같은 태그는 덮어써지지만, 사라진 태그는 끊어주지 않으면 그래프에
   계속 매달린다
3. `--reset` 은 케이스와 그 간선만 비우고 분류 체계는 보존한다
"""
import io

import numpy as np
import pytest
from PIL import Image

from app.config import Settings, get_settings
from app.ml.factory import build_models
from app.models.schemas import CaseRegisterMetadata
from app.services.agent_service import AgentService
from app.services.case_service import CaseService
from app.services.embedding_service import EmbeddingService
from app.services.reasoning_service import ReasoningService
from app.services.reconstruction_service import ReconstructionService
from app.services.roi_mask_service import ROIMaskService
from app.services.similarity_service import SimilarityService
from app.services.storage_service import LocalStorage
from app.utils.id_utils import case_key_for_source, new_case_key

from tests.fakes import _FakeRepo


def _xray_bytes(seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, size=(256, 256), dtype=np.uint8)
    arr[100:140, 130:170] = 240
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def _models():
    """모델 구성은 모듈당 한 번만, 그리고 가장 싼 어댑터로 한다.

    두 가지 이유로 그렇게 한다.

    build_models 는 PSPNet 가중치(273MB)를 올리고, 등록 한 건마다 분할이
    다시 돈다. 기본 설정 그대로면 이 파일 하나가 4분을 먹는다.

    그리고 이 테스트가 보는 것은 키 유도와 간선 정리다 - 마스크가 무엇이든
    결과가 같아야 한다. 분할기를 고정하면 그 무관함이 코드로 드러나고, ROI
    쪽 변경이 여기를 깨뜨리는 일도 없어진다.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Settings, "USE_PSPNET_ROI", False)
        mp.setattr(Settings, "USE_CV_ROI", False)
        yield build_models(get_settings())


def _build_service(build_result):
    s = get_settings()
    repo = _FakeRepo()
    svc = CaseService(
        settings=s,
        repo=repo,
        recon=ReconstructionService(build_result.anomaly),
        roi=ROIMaskService(build_result.roi),
        embedder=EmbeddingService(build_result.embedder),
        similarity=SimilarityService(repo),
        reasoning=ReasoningService(repo, s),
        agent=AgentService(s),
        storage_images=LocalStorage(s.images_dir),
        storage_recon=LocalStorage(s.recon_dir),
        storage_heatmap=LocalStorage(s.heatmap_dir),
    )
    return svc, repo


def _register(svc, *, source, tags, seed=0):
    return svc.register_case(
        image_bytes=_xray_bytes(seed),
        original_filename="view1_frontal.jpg",
        disease_tags=tags,
        finding_tags=None,
        metadata=CaseRegisterMetadata(view="PA", source="chexpert_v1.0_small"),
        case_key=case_key_for_source(source),
    )


SOURCE = "CheXpert-v1.0-small/valid/patient64541/study1/view1_frontal.jpg"


# ---------- 키 유도 ----------

def test_same_source_always_yields_the_same_key():
    assert case_key_for_source(SOURCE) == case_key_for_source(SOURCE)


def test_different_sources_yield_different_keys():
    other = "CheXpert-v1.0-small/valid/patient64542/study1/view1_frontal.jpg"
    assert case_key_for_source(SOURCE) != case_key_for_source(other)


def test_derived_key_is_a_valid_arango_key():
    """ArangoDB `_key` 가 허용하는 문자만 남아야 한다.

    원본 경로에는 슬래시와 점이 섞여 있고 길이 제한(254자)도 있다. 경로를
    그대로 키로 쓰면 등록 자체가 실패한다.
    """
    key = case_key_for_source(SOURCE)
    assert all(c.isalnum() or c in "_-.:@" for c in key)
    assert len(key) <= 254


def test_random_key_is_still_available_for_callers_that_want_one():
    """API 로 들어오는 등록은 원본 식별자가 없으므로 예전 경로가 남아야 한다."""
    assert new_case_key() != new_case_key()


# ---------- 멱등성 ----------

def test_reseeding_the_same_source_replaces_instead_of_duplicating(_models):
    """같은 원본을 두 번 적재해도 케이스는 하나다.

    이것이 깨지면 실행 횟수만큼 코퍼스가 불어나고, 유사도 검색은 같은 영상을
    서로 다른 사례로 여러 번 반환한다.
    """
    svc, repo = _build_service(_models)

    first = _register(svc, source=SOURCE, tags=["cardiomegaly"])
    second = _register(svc, source=SOURCE, tags=["cardiomegaly"])

    assert first["caseId"] == second["caseId"]
    assert len(repo.cases) == 1


def test_replacement_is_reported_as_such(_models):
    """호출자가 신규와 덮어쓰기를 구별할 수 있어야 한다.

    적재 스크립트의 요약이 이 값으로 "몇 건이 갱신됐나"를 센다. 둘 다
    "created" 로 보고하면 요약이 재실행을 신규 적재처럼 표시한다.
    """
    svc, _ = _build_service(_models)

    assert _register(svc, source=SOURCE, tags=["cardiomegaly"])["status"] == "created"
    assert _register(svc, source=SOURCE, tags=["cardiomegaly"])["status"] == "replaced"


def test_replacement_drops_edges_for_tags_that_are_gone(_models):
    """정책을 바꿔 재적재하면 예전 태그의 간선이 남으면 안 된다.

    간선 키가 case_key 에서 유도되므로 같은 태그는 덮어써진다. 그런데 이번
    등록에서 **사라진** 태그의 간선은 아무도 지우지 않으면 그대로 매달려
    있는다 - 예를 들어 --uncertainty ones 로 적재한 뒤 zeros 로 다시 적재하면
    불확실 라벨에서만 붙던 병명이 그래프에 남는다. 그래프 근거를 세는 경로가
    그것을 계속 센다.
    """
    svc, repo = _build_service(_models)

    _register(svc, source=SOURCE, tags=["cardiomegaly", "edema"])
    _register(svc, source=SOURCE, tags=["cardiomegaly"])

    targets = {e["_to"] for e in repo.edges.get("case_has_disease", [])}
    assert "diseases/cardiomegaly" in targets
    assert "diseases/edema" not in targets


def test_replacement_does_not_duplicate_edges_for_tags_that_remain(_models):
    """남아 있는 태그의 간선이 두 벌이 되지 않는다."""
    svc, repo = _build_service(_models)

    _register(svc, source=SOURCE, tags=["cardiomegaly"])
    _register(svc, source=SOURCE, tags=["cardiomegaly"])

    edges = [e for e in repo.edges.get("case_has_disease", [])
             if e["_to"] == "diseases/cardiomegaly"]
    assert len(edges) == 1


def test_new_registration_without_a_key_is_untouched(_models):
    """키를 안 주면 예전처럼 매번 새 케이스다.

    API 등록 경로(routes_cases)는 원본 식별자가 없어 키를 넘기지 않는다.
    멱등성을 그쪽까지 강제하면 서로 다른 환자의 영상이 우연히 같은 키를 받는
    일이 생길 수 있으므로, 이 동작은 그대로 둔다.
    """
    svc, repo = _build_service(_models)

    def register_without_key():
        return svc.register_case(
            image_bytes=_xray_bytes(0),
            original_filename="a.jpg",
            disease_tags=["cardiomegaly"],
            finding_tags=None,
            metadata=CaseRegisterMetadata(view="PA"),
        )

    first = register_without_key()
    second = register_without_key()

    assert first["caseId"] != second["caseId"]
    assert len(repo.cases) == 2


# ---------- reset ----------

def test_reset_clears_cases_and_their_edges(_models):
    svc, repo = _build_service(_models)
    _register(svc, source=SOURCE, tags=["cardiomegaly"])

    removed = repo.reset_cases()

    assert repo.cases == {}
    assert all(not v for v in repo.edges.values())
    assert removed["xray_cases"] == 1


def test_reset_reports_what_it_removed(_models):
    """호출자가 확인하지 않아도 되는 부수효과로 두지 않는다.

    무엇이 사라졌는지 요약에 남겨야, 지운 것과 애초에 비어 있던 것을 구별할 수
    있다.
    """
    svc, repo = _build_service(_models)
    _register(svc, source=SOURCE, tags=["cardiomegaly"])
    _register(svc, source=SOURCE + "x", tags=["edema"])

    removed = repo.reset_cases()

    assert removed["xray_cases"] == 2
    assert sum(removed.values()) > 2  # 간선도 함께 셌다


# ---------- 실제 저장소 구현 ----------
#
# 위 테스트는 _FakeRepo 를 쓴다. fake 가 reset_cases / delete_case_edges 를
# 자체 구현으로 덮고 있어서, 그 경로로는 **실제 CaseRepository 코드가 한 번도
# 돌지 않는다.** 실제로 reset 이 간선 컬렉션을 빠뜨리도록 고쳐도 위 테스트는
# 전부 통과했다. 아래는 ArangoDB 대신 최소 스텁을 물려 진짜 구현을 태운다.


class _StubCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def count(self):
        return len(self.docs)

    def truncate(self):
        self.docs.clear()

    def find(self, spec):
        return [d for d in self.docs if all(d.get(k) == v for k, v in spec.items())]

    def delete(self, key):
        self.docs = [d for d in self.docs if d.get("_key") != key]


class _StubDb:
    def __init__(self, collections):
        self._collections = collections

    def collection(self, name):
        return self._collections[name]


def _stub_repo(cases=1, edges_per_collection=2):
    from app.db.repositories import CaseRepository

    collections = {"xray_cases": _StubCollection(
        [{"_key": f"case_{i}"} for i in range(cases)])}
    for name in CaseRepository.CASE_EDGE_COLLECTIONS:
        collections[name] = _StubCollection([
            {"_key": f"case_0__t{i}", "_from": "xray_cases/case_0"}
            for i in range(edges_per_collection)
        ])
    repo = CaseRepository.__new__(CaseRepository)
    repo.db = _StubDb(collections)
    repo.settings = None
    return repo, collections


def test_real_reset_empties_the_edge_collections_too():
    """reset 이 케이스만 지우고 간선을 남기면 그래프에 고아 간선이 쌓인다.

    다음 적재가 새 케이스를 만들어도 예전 간선은 사라진 케이스를 계속 가리킨다.
    """
    repo, collections = _stub_repo()

    removed = repo.reset_cases()

    assert collections["xray_cases"].count() == 0
    for name in repo.CASE_EDGE_COLLECTIONS:
        assert collections[name].count() == 0, f"{name} 이 비워지지 않았다"
    assert removed["xray_cases"] == 1
    assert set(removed) == {"xray_cases", *repo.CASE_EDGE_COLLECTIONS}


def test_real_delete_case_edges_only_touches_that_case():
    """다른 케이스의 간선까지 지우면 안 된다."""
    repo, collections = _stub_repo()
    other = {"_key": "case_9__t0", "_from": "xray_cases/case_9"}
    collections["case_has_disease"].docs.append(other)

    removed = repo.delete_case_edges("case_0")

    assert removed == 6  # 컬렉션 3개 x 2건
    assert collections["case_has_disease"].docs == [other]


@pytest.mark.parametrize("taxonomy", ["diseases", "findings", "rois"])
def test_reset_does_not_touch_the_taxonomy(taxonomy):
    """분류 체계는 케이스와 무관하게 존재하므로 비우면 안 된다.

    지워버리면 init_db 를 다시 돌리기 전까지 등록이 전부 깨진 간선을 만든다.
    """
    from app.db.repositories import CaseRepository

    assert taxonomy not in CaseRepository.CASE_EDGE_COLLECTIONS
    assert taxonomy != "xray_cases"
