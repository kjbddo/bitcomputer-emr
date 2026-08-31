"""순위는 조회가 정하고 모델은 설명만 쓴다.

spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §3.1

라이브 6 시나리오 실측(A15·C34·D50·E03·E11·E78)에서 confidence 가 순서를
가르는 4건 전부 모델의 순서가 confidence 와 어긋났고, "일치" 2건은 세 값이
모두 같아 공허했다. 이 변경의 근거는 "confidence 가 더 잘 고른다"가 아니라
결정론·감사 가능성·중복 구조적 제거다(§3.1 "얻는 것 셋").
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"

import json  # noqa: E402

import prescription_agent  # noqa: E402
import prescription_api  # noqa: E402
from ranking import (  # noqa: E402
    MISSING_CODE,
    RANKING_STRATEGY_CANDIDATE_ORDER,
    RANKING_STRATEGY_CONFIDENCE,
    RANKING_STRATEGY_NO_CANDIDATES,
    build_ranked_slate,
    describe_ranking_strategy,
)


def _row(code, name):
    return {"prescription_code": code, "prescription_name": name}


# --- 1. 순서는 confidence 가 정한다 ---

def test_slate_order_follows_confidence_not_candidate_order():
    """D50 모양: 후보 순서와 confidence 순서가 어긋난다.

    라이브에서 D50 은 r1=0.2414 r2=0.0345 r3=0.1379 였다 — 모델이 낸 순서
    그대로면 2위가 3위보다 낮은 점수를 갖는다. 조회가 정하면 그럴 수 없다.
    """
    candidates = [_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")]
    confidence = {"C1": 0.2414, "C2": 0.0345, "C3": 0.1379}

    slate = build_ranked_slate(candidates, confidence)

    assert [c.prescription_code for c in slate] == ["C1", "C3", "C2"]
    assert [c.rank for c in slate] == [1, 2, 3]
    assert [c.confidence_score for c in slate] == [0.2414, 0.1379, 0.0345]


def test_slate_reorders_even_when_candidate_order_is_reversed():
    candidates = [_row("C3", "약3"), _row("C2", "약2"), _row("C1", "약1")]
    confidence = {"C1": 0.9, "C2": 0.5, "C3": 0.1}

    slate = build_ranked_slate(candidates, confidence)

    assert [c.prescription_code for c in slate] == ["C1", "C2", "C3"]


# --- 2. 동점 처리: 임의여도 되지만 반드시 결정론이어야 한다 ---

def test_ties_fall_back_to_candidate_order():
    """A15(0.5/0.5/0.5)·C34(0.125/0.125/0.125) 모양.

    동점 파기는 후보 목록에서 처음 등장한 순서다 — Arango 코호트 조회가
    이미 빈도 내림차순으로 준 순서라서 임의값이 아니라 조회의 순서다.
    """
    candidates = [_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")]
    confidence = {"C1": 0.5, "C2": 0.5, "C3": 0.5}

    slate = build_ranked_slate(candidates, confidence)

    assert [c.prescription_code for c in slate] == ["C1", "C2", "C3"]


def test_tie_break_is_deterministic_across_repeated_calls():
    candidates = [_row(f"C{i}", f"약{i}") for i in range(1, 9)]
    confidence = {f"C{i}": 0.125 for i in range(1, 9)}

    runs = [
        [c.prescription_code for c in build_ranked_slate(candidates, confidence)]
        for _ in range(20)
    ]

    assert len(set(map(tuple, runs))) == 1


def test_tie_break_does_not_depend_on_confidence_dict_insertion_order():
    """confidence_by_code 의 dict 삽입 순서가 순위를 바꾸면 재현성이 깨진다.

    AQL 결과 행 순서는 동점일 때 보장되지 않는다. 그 순서가 새어 들어오면
    같은 데이터에 같은 질의를 해도 화면 순서가 달라진다.
    """
    candidates = [_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")]
    forward = {"C1": 0.5, "C2": 0.5, "C3": 0.5}
    backward = {"C3": 0.5, "C2": 0.5, "C1": 0.5}

    assert [c.prescription_code for c in build_ranked_slate(candidates, forward)] == [
        c.prescription_code for c in build_ranked_slate(candidates, backward)
    ]


# --- 3. 코드 중복이 구조적으로 불가능해진다(§11.5) ---

def test_duplicate_candidate_codes_collapse_to_one_slate_row():
    """같은 처방코드가 order_line 여러 행에 나오는 것은 정상이다.

    §11.5 가 기록한 중복 추천은 모델이 같은 후보를 두 번 고른 것이었다.
    조회가 코드 단위로 접어 놓으면 그럴 수 있는 자리가 없어진다.
    """
    candidates = [
        _row("C1", "약1"),
        _row("C1", "약1"),
        _row("C2", "약2"),
        _row("C1", "약1"),
        _row("C3", "약3"),
    ]

    slate = build_ranked_slate(candidates, {"C1": 0.9, "C2": 0.5, "C3": 0.1})

    codes = [c.prescription_code for c in slate]
    assert codes == ["C1", "C2", "C3"]
    assert len(codes) == len(set(codes))


# --- 4. confidence 가 없는 경우 — 두 경우를 섞지 않는다 ---

def test_unscored_candidates_sort_after_scored_ones():
    """점수 없음은 0.0 이 아니라 '모름'이다.

    모름을 0.0 으로 읽으면 실제로 0.0 으로 조회된 후보와 구분되지 않고,
    모름을 위로 올리면 없는 근거를 주장하게 된다(GC-3 fail-closed).
    """
    candidates = [_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")]
    confidence = {"C2": 0.0}

    slate = build_ranked_slate(candidates, confidence)

    assert [c.prescription_code for c in slate] == ["C2", "C1", "C3"]
    assert slate[0].confidence_score == 0.0
    assert slate[1].confidence_score is None
    assert slate[2].confidence_score is None


def test_caller_supplied_candidates_without_confidence_keep_caller_order():
    """호출자가 top_rx 를 직접 준 경우 — confidence 가 구조적으로 없다.

    모델에게 순서를 되돌려주지 않는다. 조회(여기서는 호출자)가 준 순서를
    그대로 쓰고, 점수는 None 으로 남겨 근거가 없음을 드러낸다.
    """
    candidates = [_row("C7", "약7"), _row("C1", "약1"), _row("C4", "약4")]

    slate = build_ranked_slate(candidates, {})

    assert [c.prescription_code for c in slate] == ["C7", "C1", "C4"]
    assert all(c.confidence_score is None for c in slate)
    assert describe_ranking_strategy(slate) == RANKING_STRATEGY_CANDIDATE_ORDER


def test_strategy_label_distinguishes_the_three_cases():
    scored = build_ranked_slate([_row("C1", "약1")], {"C1": 0.3})
    unscored = build_ranked_slate([_row("C1", "약1")], {})
    empty = build_ranked_slate([], {})

    assert describe_ranking_strategy(scored) == RANKING_STRATEGY_CONFIDENCE
    assert describe_ranking_strategy(unscored) == RANKING_STRATEGY_CANDIDATE_ORDER
    assert describe_ranking_strategy(empty) == RANKING_STRATEGY_NO_CANDIDATES


def test_non_numeric_confidence_is_unknown_not_zero():
    slate = build_ranked_slate(
        [_row("C1", "약1"), _row("C2", "약2")], {"C1": "높음", "C2": 0.1}
    )

    assert [c.prescription_code for c in slate] == ["C2", "C1"]
    assert slate[1].confidence_score is None


def test_empty_candidates_yields_empty_slate():
    assert build_ranked_slate([], {"C1": 0.9}) == []
    assert build_ranked_slate([{"note": "데이터 부족: top_rx 비어 있음"}], {}) == []


# --- 5. 배선: recommend() 가 모델 출력이 아니라 slate 를 쓴다 ---

def _fixed_llm(monkeypatch, payload):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setattr(
        prescription_api,
        "_invoke_gateway_json",
        lambda system_prompt, user_prompt, model: json.dumps(payload, ensure_ascii=False),
    )


def _model_items(codes, names):
    """모델이 낸 답. 길이는 slate 길이와 같아야 한다(설계 §3.2)."""
    return {
        "prescriptions": [
            {
                "rank": i + 1,
                "name": names[i],
                "prescription_code": codes[i],
                "dosage": "미기재",
                "reason": f"모델이 쓴 {i + 1}순위 설명",
            }
            for i in range(len(codes))
        ]
    }


def _three_items(codes, names):
    return _model_items(codes[:3], names[:3])


def _request(**kwargs):
    base = dict(
        patient_id="p-rank-1",
        symptoms="발열",
        history="특이사항 없음",
        fetch_top_rx_from_arango=False,
        fetch_cohort_rx_from_arango=False,
    )
    base.update(kwargs)
    return prescription_api.PrescriptionRecommendRequest(**base)


def test_recommend_uses_confidence_order_not_model_order(monkeypatch):
    """모델이 낸 순서가 confidence 와 어긋나도 응답은 confidence 순이다."""
    monkeypatch.setattr(
        prescription_api,
        "fetch_confidence_scores_by_diagnosis_codes",
        lambda *a, **k: [
            {"prescription_code": "C1", "confidence_score": 0.2414},
            {"prescription_code": "C2", "confidence_score": 0.0345},
            {"prescription_code": "C3", "confidence_score": 0.1379},
        ],
    )
    _fixed_llm(monkeypatch, _three_items(["C1", "C2", "C3"], ["약1", "약2", "약3"]))

    resp = prescription_api.recommend(
        _request(
            top_rx=[_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")],
            disease_codes=["D50"],
        ),
        x_prescription_eval_trace=None,
    )

    assert [p.prescription_code for p in resp.prescriptions] == ["C1", "C3", "C2"]
    assert [p.rank for p in resp.prescriptions] == [1, 2, 3]
    assert [p.confidence_score for p in resp.prescriptions] == [0.2414, 0.1379, 0.0345]


def test_model_cannot_substitute_code_or_name(monkeypatch):
    """모델이 후보 밖의 코드·이름을 내도 응답에는 조회 결과가 실린다."""
    monkeypatch.setattr(
        prescription_api,
        "fetch_confidence_scores_by_diagnosis_codes",
        lambda *a, **k: [{"prescription_code": "C1", "confidence_score": 0.4}],
    )
    _fixed_llm(
        monkeypatch,
        _three_items(
            ["지어낸1", "지어낸2", "지어낸3"], ["슈퍼관절완치캡슐", "가짜약2", "가짜약3"]
        ),
    )

    resp = prescription_api.recommend(
        _request(
            top_rx=[_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")],
            disease_codes=["D50"],
        ),
        x_prescription_eval_trace=None,
    )

    assert [p.prescription_code for p in resp.prescriptions] == ["C1", "C2", "C3"]
    assert [p.name for p in resp.prescriptions] == ["약1", "약2", "약3"]
    # 모델에게 남는 것은 설명뿐이다(§3.1 "모델에게 남는 일").
    assert [p.reason for p in resp.prescriptions] == [
        "모델이 쓴 1순위 설명",
        "모델이 쓴 2순위 설명",
        "모델이 쓴 3순위 설명",
    ]


def test_model_reason_follows_the_slate_rank_not_the_model_rank(monkeypatch):
    """모델이 rank 를 뒤집어 내도 설명은 slate 순위에 맞춰 붙는다."""
    monkeypatch.setattr(
        prescription_api,
        "fetch_confidence_scores_by_diagnosis_codes",
        lambda *a, **k: [
            {"prescription_code": "C1", "confidence_score": 0.9},
            {"prescription_code": "C2", "confidence_score": 0.5},
            {"prescription_code": "C3", "confidence_score": 0.1},
        ],
    )
    payload = _three_items(["C3", "C2", "C1"], ["약3", "약2", "약1"])
    _fixed_llm(monkeypatch, payload)

    resp = prescription_api.recommend(
        _request(
            top_rx=[_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")],
            disease_codes=["D50"],
        ),
        x_prescription_eval_trace=None,
    )

    assert [p.prescription_code for p in resp.prescriptions] == ["C1", "C2", "C3"]
    assert resp.prescriptions[0].reason == "모델이 쓴 1순위 설명"


def test_response_codes_are_unique_when_candidates_repeat_a_code(monkeypatch):
    """§11.5 중복이 구조적으로 불가능하다 — 모델이 같은 코드를 세 번 내도."""
    monkeypatch.setattr(
        prescription_api,
        "fetch_confidence_scores_by_diagnosis_codes",
        lambda *a, **k: [],
    )
    _fixed_llm(monkeypatch, _model_items(["C1", "C1"], ["약1", "약1"]))

    resp = prescription_api.recommend(
        _request(
            top_rx=[_row("C1", "약1"), _row("C1", "약1"), _row("C2", "약2")],
        ),
        x_prescription_eval_trace=None,
    )

    # 후보가 (중복을 접고) 2건이므로 응답도 2건이다 — 세 번째 칸이 없다.
    real_codes = [p.prescription_code for p in resp.prescriptions]
    assert real_codes == ["C1", "C2"]
    assert len(real_codes) == len(set(real_codes))
    # 전체 status 는 보지 않는다 — 이 픽스처의 "C1"·"C2"는 9자리 약제 코드가
    # 아니라서 code_is_medication 이 정당하게 flag 한다(그 검사와 무관한 주장이다).
    schema = [c for c in resp.verification["checks"] if c["id"] == "schema_top3"]
    assert len(schema) == 1
    assert schema[0]["outcome"] == "ok"
    assert "코드중복=0건" in schema[0]["evidence"]


# --- 6. confidence 가 없는 두 경우 ---

def test_caller_supplied_top_rx_leaves_confidence_none_not_zero(monkeypatch):
    """호출자 top_rx 는 confidence 가 구조적으로 없다 — 0.0 으로 위장하지 않는다.

    M-4 가 기록한 한계(조회된 0.0 과 폴백된 0.0 이 구분되지 않음)는 순위가
    confidence 에 걸리는 순간 한계가 아니라 결함이 된다. None 으로 남긴다.
    """
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    # 모델은 후보 순서를 뒤집어 낸다 — confidence 가 없다고 해서 순서를 모델에게
    # 되돌려주면 여기서 응답이 C3·C2·C1 이 된다.
    _fixed_llm(monkeypatch, _three_items(["C3", "C2", "C1"], ["약3", "약2", "약1"]))

    resp = prescription_api.recommend(
        _request(top_rx=[_row("C1", "약1"), _row("C2", "약2"), _row("C3", "약3")]),
        x_prescription_eval_trace=None,
    )

    assert [p.confidence_score for p in resp.prescriptions] == [None, None, None]
    assert [p.prescription_code for p in resp.prescriptions] == ["C1", "C2", "C3"]
    assert [p.name for p in resp.prescriptions] == ["약1", "약2", "약3"]
    # 근거가 없으면 통과가 아니다(GC-2). 구조 검사 confidence_in_range 는 skipped.
    conf_checks = [
        c for c in resp.verification["checks"] if c["id"] == "confidence_in_range"
    ]
    assert conf_checks and all(c["outcome"] == "skipped" for c in conf_checks)


def test_zero_candidates_yield_an_empty_response(monkeypatch):
    """E78: 약제 후보 0건. 빈손을 3건으로 채우지 않는다(설계 §3.2).

    예전에는 조회층이 쓴 플레이스홀더 3건이 나왔다. 이제는 0건이다.
    """
    monkeypatch.setattr(prescription_api, "fetch_top_rx_from_arango", lambda *a, **k: [])
    monkeypatch.setattr(
        prescription_api, "fetch_cohort_prescriptions_by_diagnosis_codes", lambda *a, **k: []
    )
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    _fixed_llm(
        monkeypatch,
        _three_items(
            ["AB123", "CD456", "EF789"], ["아토르바스타틴", "로수바스타틴", "페노피브레이트"]
        ),
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

    # 후보가 0건이면 응답도 0건이다 — 플레이스홀더 세 칸으로 채우지 않는다
    # (설계 §3.2). 모델은 호출조차 되지 않으므로 위 _fixed_llm 페이로드는
    # 어디에도 실릴 수 없다.
    assert resp.prescriptions == []
    blob = json.dumps(resp.model_dump(), ensure_ascii=False)
    assert "아토르바스타틴" not in blob
    assert resp.used_arango_top_rx is False
    assert resp.used_cohort_rx is False
    assert resp.verification["status"] == "skipped"


def test_partial_slate_stops_at_the_last_supported_rank(monkeypatch):
    """후보가 1건뿐이면 응답도 1건이다 — 2·3순위를 만들지 않는다(설계 §3.2).

    예전에는 남는 두 칸을 플레이스홀더로 채웠다. 그것도 지어내기는 아니었지만
    "3순위는 여기 있습니다 — 다만 없습니다" 라고 말하는 형식이었다.
    """
    monkeypatch.setattr(
        prescription_api, "fetch_confidence_scores_by_diagnosis_codes", lambda *a, **k: []
    )
    _fixed_llm(monkeypatch, _model_items(["C1"], ["약1"]))

    resp = prescription_api.recommend(
        _request(top_rx=[_row("C1", "약1")]),
        x_prescription_eval_trace=None,
    )

    assert len(resp.prescriptions) == 1
    assert resp.prescriptions[0].prescription_code == "C1"
    assert resp.prescriptions[0].rank == 1


def test_ranking_strategy_is_recorded_in_tool_trace(monkeypatch):
    monkeypatch.setattr(
        prescription_api,
        "fetch_confidence_scores_by_diagnosis_codes",
        lambda *a, **k: [{"prescription_code": "C1", "confidence_score": 0.4}],
    )
    _fixed_llm(monkeypatch, _model_items(["C1", "C2"], ["약1", "약2"]))

    resp = prescription_api.recommend(
        _request(
            top_rx=[_row("C1", "약1"), _row("C2", "약2")],
            disease_codes=["D50"],
        ),
        x_prescription_eval_trace="1",
    )

    rows = [r for r in resp.toolTrace if r["tool"] == "prescription_ranking"]
    assert len(rows) == 1
    assert rows[0]["strategy"] == RANKING_STRATEGY_CONFIDENCE
    assert rows[0]["scoredCandidates"] == 1
    assert rows[0]["slateSize"] == 2


# --- 7. _sparse_override 제거 ---

def test_prompt_has_no_sparse_override_section():
    """순위가 조회로 고정되면 '부족하면 실제 제품명을 채우라'는 분기는 모순이다.

    §11.8.2 의 '모델은 지어내지 않는다' 관측은 이 분기가 걸리지 않았다는
    조건부였다(§1.1). 분기를 없애면 조건이 사라진다.
    """
    assert not hasattr(prescription_agent, "_sparse_top_rx_appendix")

    prompt = prescription_agent.build_prescription_agent_prompt(
        patient_id="p1",
        symptoms="발열",
        history="",
        top_rx=[_row("C1", "약1")],
        similar_outcomes="",
        ranked_slate=[
            {"rank": 1, "name": "약1", "prescription_code": "C1", "confidence_score": 0.4}
        ],
    )

    assert "Sparse data override" not in prompt
    assert "실제 국내 처방명" not in prompt
    assert "임상적으로 타당한 병용·대안 처방" not in prompt


def test_prompt_carries_the_rendered_slate_rows():
    """slate 가 프롬프트에 실제로 실려야 모델의 reason 이 확정 순위에 붙는다.

    순위·코드·이름은 서비스가 덮어쓰므로 slate 가 빠져도 응답 순서는 맞다.
    빠졌을 때 조용히 망가지는 것은 **설명**이다 — 모델이 자기가 고른 다른 약에
    대해 쓴 문장이 조회가 고른 약의 근거로 화면에 붙는다. top_rx 블록에도 같은
    이름·코드가 들어 있으므로, 이름 존재 여부가 아니라 렌더된 slate 행 자체를
    본다(그렇게 하지 않으면 이 테스트가 slate 제거를 놓친다).
    """
    prompt = prescription_agent.build_prescription_agent_prompt(
        patient_id="p1",
        symptoms="발열",
        history="",
        top_rx=[_row("C1", "약1"), _row("C2", "약2")],
        similar_outcomes="",
        ranked_slate=[
            {"rank": 1, "name": "약1", "prescription_code": "C1", "confidence_score": 0.4},
            {"rank": 2, "name": "약2", "prescription_code": "C2", "confidence_score": None},
        ],
    )

    assert "확정된 추천 순위" in prompt
    assert "1. name='약1'  prescription_code='C1'  — confidence 0.4000" in prompt
    assert "2. name='약2'  prescription_code='C2'  — confidence 없음" in prompt


def test_prompt_for_zero_candidates_is_never_built():
    """후보 0건이면 프롬프트 자체가 만들어지지 않는다(설계 §3.2).

    예전에는 "세 항목 모두 플레이스홀더로 두십시오" 라고 지시하는 빈 slate
    블록이 있었다. 응답이 후보 수만큼만 길어진 지금 그런 답은 존재하지 않고,
    빈 slate 로 여기까지 오는 것은 배선 결함이다 — 조용히 문자열을 만들면
    모델에게 빈손을 주고 그 출력이 어디로 갈지가 다시 열린다.
    """
    import pytest

    with pytest.raises(ValueError):
        prescription_agent.build_prescription_agent_prompt(
            patient_id="p1",
            symptoms="건강검진에서 콜레스테롤 높다고 들었다",
            history="",
            top_rx=[{"note": "데이터 부족: top_rx 비어 있음"}],
            similar_outcomes="",
            ranked_slate=[],
        )


def test_prompt_requires_ranked_slate_argument():
    """slate 없이 프롬프트를 만들 수 있으면 순위가 조용히 모델에게 돌아간다."""
    import inspect

    sig = inspect.signature(prescription_agent.build_prescription_agent_prompt)
    param = sig.parameters["ranked_slate"]
    assert param.default is inspect.Parameter.empty
