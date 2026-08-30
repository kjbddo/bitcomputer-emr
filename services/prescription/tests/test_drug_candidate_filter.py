"""후보 조회가 약제만 올리는지, 약제가 0건일 때 정직하게 떨어지는지 (F-H1).

조회 AQL 은 라이브 DB 없이 실행할 수 없으므로, 여기서는 두 가지를 본다.
  1. 쿼리 텍스트가 공유 술어(MEDICATION_CODE_AQL_PREDICATE)를 실제로 담고
     있고 정규식을 바인드 변수로 넘기는가 — 필터를 빼면 빨개진다.
  2. 필터 결과가 0건일 때 필터를 푼 재조회로 폴백하지 않는가 —
     `_aql_rows` 호출 횟수로 본다. 폴백을 넣으면 두 번 불린다.
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")

import pytest  # noqa: E402

import run_graph_qa  # noqa: E402
import run_prescription_agent as rpa  # noqa: E402
from medication_codes import (  # noqa: E402
    MEDICATION_CODE_AQL_PREDICATE,
    MEDICATION_CODE_REGEX,
    MEDICATION_CODE_BIND_KEY,
)

ORDER_LINE_CODE_EXPR = "ol.`처방코드_norm`"


@pytest.fixture
def spy_aql(monkeypatch):
    """Arango 연결을 우회하고 _aql_rows 호출을 기록한다."""
    calls = []

    def fake_rows(db, aql, bind=None, **kwargs):
        calls.append({"aql": aql, "bind": dict(bind or {})})
        return []

    monkeypatch.setattr(run_graph_qa, "load_arango_config", lambda *a, **k: {})
    monkeypatch.setattr(run_graph_qa, "connect_arango", lambda *a, **k: object())
    monkeypatch.setattr(run_graph_qa, "_aql_rows", fake_rows)
    monkeypatch.delenv("PRESCRIPTION_EVAL_SKIP_ARANGO", raising=False)
    return calls


# --- 1. 필터가 쿼리 안에 실제로 있는가 ---

def test_cohort_aql_filters_candidates_to_medication_codes():
    predicate = MEDICATION_CODE_AQL_PREDICATE.format(code=ORDER_LINE_CODE_EXPR)
    assert predicate in rpa._COHORT_AQL


def test_top_rx_aql_filters_candidates_to_medication_codes(spy_aql):
    rpa.fetch_top_rx_from_arango("530524451")
    predicate = MEDICATION_CODE_AQL_PREDICATE.format(code=ORDER_LINE_CODE_EXPR)
    assert predicate in spy_aql[0]["aql"]


@pytest.mark.parametrize(
    "call",
    [
        lambda: rpa.fetch_top_rx_from_arango("530524451"),
        lambda: rpa.fetch_cohort_prescriptions_by_diagnosis_codes(["E11"]),
    ],
)
def test_candidate_queries_bind_the_shared_regex(spy_aql, call):
    """AQL 과 파이썬 판정이 같은 정규식을 쓴다 — 갈라지면 조회에서 걸러진
    것과 code_is_medication 이 잡는 것이 어긋난다."""
    call()
    assert spy_aql[0]["bind"][MEDICATION_CODE_BIND_KEY] == MEDICATION_CODE_REGEX


# --- 2. 0건일 때 정직하게 떨어지는가 ---

@pytest.mark.parametrize(
    "call",
    [
        lambda: rpa.fetch_top_rx_from_arango("530524451"),
        lambda: rpa.fetch_cohort_prescriptions_by_diagnosis_codes(["E78"]),
    ],
)
def test_zero_medication_candidates_does_not_fall_back_to_unfiltered(spy_aql, call):
    """약제가 0건이면 빈 결과를 그대로 돌려준다.

    E78(고지혈증)이 라이브에서 실제로 이 경우다 — 연결된 order_line 14행
    전부가 수가·검사라 약제는 0건이다. 여기서 필터를 푼 재조회로 폴백하면
    수가 라인이 후보로 올라가고, code_in_candidates 가 그 수가 코드에
    ok 를 내어 응답이 passed 로 나간다. 없는 근거를 만들어내는 것이므로
    GC-2 위반이다.
    """
    rows = call()

    assert rows == []
    assert len(spy_aql) == 1, "필터를 푼 재조회(폴백)가 들어갔다"
