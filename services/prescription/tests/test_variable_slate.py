"""응답은 조회가 뒷받침하는 만큼만 길다 — 3칸을 채우지 않는다.

spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §3.2
(§8 순서의 2번 나머지 절반. `_sparse_override` 제거는 step 1 에서 이미 끝났다.)

**왜.** §11.8.2 실측: 맹장염 양상에 무좀연고·인공눈물만 후보로 줬을 때 모델이
무좀연고를 두 번 추천했다. 프롬프트가 3건을 요구했고 모델은 계약을 지켰다.
퇴화는 모델의 결함이 아니라 계약이 만든 것이다.

**무엇이 바뀌나.** `build_ranked_slate` 는 원래부터 조회가 뒷받침하는 만큼만
돌려줬다. 그 뒤에서 `prescription_api` 가 `range(SLATE_SIZE)` 로 세 칸을 채우며
빈 순위에 플레이스홀더를 넣었다. "3순위는 여기 있습니다 — 다만 없습니다" 는
없는 것을 있다고 말하는 형식이다. 그 패딩을 없앤다.
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"

import inspect  # noqa: E402
import json  # noqa: E402

import prescription_agent  # noqa: E402
import prescription_api  # noqa: E402
import pytest  # noqa: E402
from ranking import SLATE_SIZE  # noqa: E402
from verification import verify_prescriptions  # noqa: E402


def _row(code, name):
    return {"prescription_code": code, "prescription_name": name}


def _request(**kwargs):
    base = dict(
        patient_id="p-variable-slate",
        symptoms="우하복부 압통, 구역, 미열",
        history="특이사항 없음",
        fetch_top_rx_from_arango=False,
        fetch_cohort_rx_from_arango=False,
    )
    base.update(kwargs)
    return prescription_api.PrescriptionRecommendRequest(**base)


def _fixed_llm(monkeypatch, payload):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setattr(
        prescription_api,
        "_invoke_gateway_json",
        lambda system_prompt, user_prompt, model: json.dumps(payload, ensure_ascii=False),
    )


def _model_rows(n):
    return {
        "prescriptions": [
            {
                "rank": i + 1,
                "name": f"모델이 쓴 이름{i + 1}",
                "prescription_code": f"모델코드{i + 1}",
                "dosage": "미기재",
                "reason": f"모델이 쓴 {i + 1}순위 설명",
            }
            for i in range(n)
        ]
    }


class _Item:
    def __init__(self, rank, code="123456789", name="약", confidence=None):
        self.rank = rank
        self.prescription_code = code
        self.name = name
        self.confidence_score = confidence


# ---------------------------------------------------------------------------
# 1. 응답 길이는 조회가 정한다
# ---------------------------------------------------------------------------

def test_two_candidates_yield_two_items_not_three(monkeypatch):
    """§11.8.2 의 모양. 후보 2건이면 응답도 2건이다 — 세 번째 칸이 없다."""
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    _fixed_llm(monkeypatch, _model_rows(2))

    resp = prescription_api.recommend(
        _request(top_rx=[_row("111111111", "무좀연고"), _row("222222222", "인공눈물")]),
        x_prescription_eval_trace=None,
    )

    assert len(resp.prescriptions) == 2
    assert [p.rank for p in resp.prescriptions] == [1, 2]
    assert [p.prescription_code for p in resp.prescriptions] == ["111111111", "222222222"]
    # 같은 약이 두 번 실리지 않는다 — 채울 칸 자체가 없으므로.
    codes = [p.prescription_code for p in resp.prescriptions]
    assert len(codes) == len(set(codes))


def test_single_candidate_yields_one_item(monkeypatch):
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    _fixed_llm(monkeypatch, _model_rows(1))

    resp = prescription_api.recommend(
        _request(top_rx=[_row("111111111", "무좀연고")]),
        x_prescription_eval_trace=None,
    )

    assert len(resp.prescriptions) == 1
    assert resp.prescriptions[0].rank == 1
    # 플레이스홀더 행이 응답 어디에도 남지 않는다.
    blob = json.dumps(resp.model_dump(), ensure_ascii=False)
    assert "데이터 부족: 조회된 처방 후보 없음" not in blob


def test_response_never_exceeds_slate_size(monkeypatch):
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    _fixed_llm(monkeypatch, _model_rows(3))

    resp = prescription_api.recommend(
        _request(top_rx=[_row(f"{i}" * 9, f"약{i}") for i in range(1, 6)]),
        x_prescription_eval_trace=None,
    )

    assert len(resp.prescriptions) == SLATE_SIZE


# ---------------------------------------------------------------------------
# 2. 0건은 실패가 아니다
# ---------------------------------------------------------------------------

def test_zero_candidates_yield_an_empty_list_not_placeholders(monkeypatch):
    """E78(고지혈증)은 PR #9 필터 이후 실제로 약제 후보가 0건이다.

    빈 목록은 "우리 데이터가 이 상병에 대한 처방을 뒷받침하지 않는다" 는
    답이지 오류가 아니다.
    """
    monkeypatch.setattr(prescription_api, "fetch_top_rx_from_arango", lambda *a, **k: [])
    monkeypatch.setattr(
        prescription_api, "fetch_cohort_prescriptions_by_diagnosis_codes", lambda *a, **k: []
    )
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )

    resp = prescription_api.recommend(
        _request(
            patient_id="p-e78",
            top_rx=[],
            disease_codes=["E78"],
            fetch_top_rx_from_arango=True,
            fetch_cohort_rx_from_arango=True,
        ),
        x_prescription_eval_trace=None,
    )

    assert resp.prescriptions == []
    # 실패와 구분되는 상태가 응답에 실려 있다. 이미 있는 축을 쓴다 —
    # 새 필드를 만들지 않는다.
    assert resp.used_arango_top_rx is False
    assert resp.arango_top_rx_count == 0
    assert resp.used_cohort_rx is False
    assert resp.cohort_rx_count == 0
    assert resp.verification["status"] == "skipped"
    assert resp.verification["skippedReason"]


def test_zero_candidates_do_not_call_the_model(monkeypatch):
    """설명할 항목이 0건이면 모델에게 시킬 일이 없다.

    호출하면 토큰만 쓰고, 모델 출력이 응답에 새어 들어갈 자리를 만든다.
    """
    monkeypatch.setattr(prescription_api, "fetch_top_rx_from_arango", lambda *a, **k: [])
    monkeypatch.setattr(
        prescription_api, "fetch_cohort_prescriptions_by_diagnosis_codes", lambda *a, **k: []
    )
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    monkeypatch.setenv("LLM_PROVIDER", "real")

    def _explode(*args, **kwargs):
        raise AssertionError("후보가 0건인데 게이트웨이를 호출했다")

    monkeypatch.setattr(prescription_api, "_invoke_gateway_json", _explode)

    resp = prescription_api.recommend(
        _request(
            patient_id="p-e78",
            top_rx=[],
            disease_codes=["E78"],
            fetch_top_rx_from_arango=True,
            fetch_cohort_rx_from_arango=True,
        ),
        x_prescription_eval_trace=None,
    )

    assert resp.prescriptions == []
    # llmStatus 는 "모델이 돌았나" 다. 돌지 않았으면 real 이라고 말하지 않는다.
    assert resp.llmStatus == "skipped"
    # engineStatus 는 "어떤 provider 로 설정돼 있나" 로 축이 다르다.
    assert resp.engineStatus == "real"


def test_llm_status_enum_admits_skipped():
    schema = prescription_api.PrescriptionRecommendResponse.model_json_schema()
    assert schema["properties"]["llmStatus"].get("enum") == ["real", "stub", "skipped"]


# ---------------------------------------------------------------------------
# 3. schema_top3 — 순위 무결성의 새 정의
# ---------------------------------------------------------------------------
#
# 이전 정의는 `sorted(ranks) == [1, 2, 3]` 이었다. 길이가 가변이 된 지금 그
# 상수를 그대로 두면 정상 응답(1건·2건)을 전부 flag 하고, 반대로 조건을 지우면
# 검사가 공허해진다. 새 정의는 세 가지를 함께 본다:
#   - rank 는 1부터 빈틈·중복 없이 이어지는가 (`[1..N]`)
#   - N 이 조회 상한(SLATE_SIZE)을 넘지 않는가 — "top-≤3" 의 3이 여기 남는다
#   - 실제 코드가 중복되지 않는가 (기존 §11.5 방어 유지)

def _schema_check(items):
    result = verify_prescriptions(candidates=[], items=items)
    found = [c for c in result.checks if c.id == "schema_top3"]
    assert len(found) == 1
    return found[0]


def test_schema_top3_accepts_a_two_item_response():
    assert _schema_check([_Item(1, "111111111"), _Item(2, "222222222")]).outcome == "ok"


def test_schema_top3_accepts_a_one_item_response():
    assert _schema_check([_Item(1, "111111111")]).outcome == "ok"


def test_schema_top3_accepts_an_empty_response():
    """0건도 온전한 응답이다 — 형식이 깨진 것이 아니다."""
    check = _schema_check([])
    assert check.outcome == "ok"
    assert "항목수=0" in check.evidence


def test_schema_top3_flags_a_rank_gap():
    assert _schema_check([_Item(1, "111111111"), _Item(3, "333333333")]).outcome == "flagged"


def test_schema_top3_flags_ranks_that_do_not_start_at_one():
    assert _schema_check([_Item(2, "222222222"), _Item(3, "333333333")]).outcome == "flagged"


def test_schema_top3_flags_duplicate_ranks():
    assert _schema_check([_Item(1, "111111111"), _Item(1, "222222222")]).outcome == "flagged"


def test_schema_top3_flags_more_items_than_the_slate_cap():
    """상한을 넘겨 부풀린 응답은 여전히 위반이다 — "top-≤3" 의 3."""
    items = [_Item(i, f"{i}" * 9) for i in range(1, SLATE_SIZE + 2)]
    assert _schema_check(items).outcome == "flagged"


def test_schema_top3_still_flags_duplicate_codes():
    check = _schema_check([_Item(1, "111111111"), _Item(2, "111111111")])
    assert check.outcome == "flagged"
    assert "코드중복=1건" in check.evidence


def test_schema_top3_is_not_vacuous_for_a_full_slate():
    ok = _schema_check([_Item(1, "111111111"), _Item(2, "222222222"), _Item(3, "333333333")])
    assert ok.outcome == "ok"
    bad = _schema_check([_Item(1, "111111111"), _Item("first", "222222222")])
    assert bad.outcome == "flagged"


# ---------------------------------------------------------------------------
# 4. 프롬프트가 3건을 요구하지 않는다
# ---------------------------------------------------------------------------

def test_prompt_asks_for_exactly_the_slate_row_count():
    prompt = prescription_agent.build_prescription_agent_prompt(
        patient_id="p1",
        symptoms="우하복부 압통",
        history="",
        top_rx=[_row("111111111", "무좀연고"), _row("222222222", "인공눈물")],
        similar_outcomes="",
        ranked_slate=[
            {"rank": 1, "name": "무좀연고", "prescription_code": "111111111",
             "confidence_score": 0.4},
            {"rank": 2, "name": "인공눈물", "prescription_code": "222222222",
             "confidence_score": None},
        ],
    )

    assert "확정된 2개 순위" in prompt
    assert "확정된 3개 순위" not in prompt
    # 예시 JSON 이 rank 3 을 요구하면 모델은 빈 칸을 채우려 한다.
    assert '"rank": 3' not in prompt


def test_prompt_refuses_an_empty_slate():
    """설명할 항목이 없는데 프롬프트를 만들 수 있으면 모델에게 빈손을 준다."""
    with pytest.raises(ValueError):
        prescription_agent.build_prescription_agent_prompt(
            patient_id="p1",
            symptoms="건강검진에서 콜레스테롤 높다고 들었다",
            history="",
            top_rx=[{"note": "데이터 부족: top_rx 비어 있음"}],
            similar_outcomes="",
            ranked_slate=[],
        )


# ---------------------------------------------------------------------------
# 5. 파서가 3건을 강제하지 않는다 — 대신 slate 길이와 맞춘다
# ---------------------------------------------------------------------------

def test_validate_payload_requires_an_explicit_expected_count():
    """기본값이 있으면 호출자가 빠뜨렸을 때 조용히 3으로 되돌아간다."""
    sig = inspect.signature(prescription_agent.validate_prescriptions_payload)
    param = sig.parameters["expected_count"]
    assert param.default is inspect.Parameter.empty


def test_validate_payload_accepts_a_two_row_answer():
    data = _model_rows(2)
    rows = prescription_agent.validate_prescriptions_payload(data, expected_count=2)
    assert [r["rank"] for r in rows] == [1, 2]


def test_validate_payload_rejects_a_padded_answer():
    """slate 가 2건인데 모델이 3건을 내면 그 한 건은 근거가 없다."""
    with pytest.raises(ValueError):
        prescription_agent.validate_prescriptions_payload(_model_rows(3), expected_count=2)


def test_validate_payload_rejects_a_short_answer():
    with pytest.raises(ValueError):
        prescription_agent.validate_prescriptions_payload(_model_rows(1), expected_count=2)


# ---------------------------------------------------------------------------
# 6. 스텁도 slate 길이를 따른다
# ---------------------------------------------------------------------------

def test_stub_response_matches_the_slate_length(monkeypatch):
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    monkeypatch.setenv("LLM_PROVIDER", "stub")

    resp = prescription_api.recommend(
        _request(top_rx=[_row("111111111", "무좀연고"), _row("222222222", "인공눈물")]),
        x_prescription_eval_trace=None,
    )

    assert resp.llmStatus == "stub"
    assert len(resp.prescriptions) == 2
