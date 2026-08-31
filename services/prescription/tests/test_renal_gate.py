"""신기능 금기 관문 — 설계 §3.3.

spec: Docs/superpowers/specs/2026-08-30-ai-service-redesign-design.md §1.3, §3.3

여기서 쓰는 노트 문자열은 전부 **라이브 그래프의 실제 문자열**이다
(2026-08-31, ArangoDB `bitcomputer_graph`, special_notes 1,025행 중
신기능 관련 표현이 든 136행). 지어낸 형식으로 파서를 시험하면 파서가
현실이 아니라 테스트에 맞춰 자란다.
"""
import os

os.environ.setdefault("ARANGO_PASSWORD", "test-only-not-used")
os.environ["LLM_PROVIDER"] = "stub"

import pytest  # noqa: E402

import renal_gate as rg  # noqa: E402


# --- 라이브 그래프에서 그대로 가져온 노트 -----------------------------------

# VISIT_530222900 외 12건. GFR 13 + 신부전 4/5단계.
NOTE_GFR13 = (
    "우측대퇴골자간골절 당뇨 고혈압 치매 신부전 4/5단계 26/1/19 "
    "cystatin c 3.29 GFR 13 10/20260203///5/20260203"
)
# VISIT_530472595. 이 방문이 **실제로** 다이아벡스정500mg(메트포르민)을 받았다.
NOTE_DM_CKD = (
    "[6ya / 6.4%['25.08]), DM-CKD, L-spine disc - 3등급 / L2110098856 "
    "-25년 11월에는 하모닐란액 처방 안 됨."
)
# VISIT_530267425 외. HTML 조각 + 괄호 안 병기 + 날짜.
NOTE_CKD_3B = (
    '<span style="background-color: rgb(102, 185, 102);">당뇨치료제3종초과로 '
    "메트폴엠정 본인부담100으로 변경필요 </span> - CKD(3b, 24'.08) 고혈압 "
    "당뇨(인슐린) 퇴행성질환 치매 t-score -3.5 (20240724) "
    "12/20240102///6/20240102 L-tube"
)
# VISIT_530506338 외. 로마 숫자 병기.
NOTE_CKD_ROMAN = (
    "재택형 Dementia, CKDIV, Anemia - <strong>5등급 / L2505069234</strong> - "
    "00/20250421///5/20250421 -MMSE/GDS 20/4 (2026. 3. 5. 의원 체크)"
)
# VISIT_530293778 외 25건. r/o = rule out = **의심**이지 확진이 아니다.
NOTE_RO_CKD = (
    "v810 f001 02/20240724///6/20240724 Dementia, HTN, Pleural effusion "
    "r/o CKD or CHF h/o femur fx ('23 화성유일), h/o chole ('23.04) MMSE (-)"
)
# VISIT_530271563 외. eGFR 소수점.
NOTE_EGFR = (
    "00/20250120///6/20250120 HTN, DM, Hypothyroidism, Stroke, Dementia, IDA - "
    "가루약 ['25.02] Hb 8.8, BUN/Cr 32.7/1.3, eGFR 39.9, TSH 31"
)
# VISIT_530406625 외. 투석.
NOTE_DIALYSIS = (
    "가루약 G3101 v800 치매 당뇨 갑상선기능저하증 신우신염 (30년전 투석) "
    "L-tube(+) 00/20250623///6/20250623"
)
# VISIT_530442619. 심부전(heart failure)은 신부전이 아니다.
NOTE_HEART_FAILURE = "심부전 갑상선 항진증"
# VISIT_530486376. 신장 언급은 있으나 기능 저하 지표가 아니다.
NOTE_KIDNEY_WATER = (
    "foley(+)L-tube(+) 우측편마비, 신장에 물..생김, 우울증, 치매, 변비 "
    "06/20250123///6/20250123 26.01 0/6"
)
# 신기능 언급이 아예 없는 노트(special_notes 다수가 이 모양이다).
NOTE_NO_RENAL = "치매 고혈압 관절염"

# 라이브 그래프의 실제 처방명.
DRUG_METFORMIN = "다이아벡스정500mg"
DRUG_NOT_IN_TABLE = "훼로바-유서방정"


def _item(rank, name, code="641600390"):
    return {"rank": rank, "name": name, "prescription_code": code}


# --- 1. 자유텍스트 파싱 -------------------------------------------------------


@pytest.mark.parametrize(
    "note",
    [NOTE_GFR13, NOTE_DM_CKD, NOTE_CKD_3B, NOTE_CKD_ROMAN, NOTE_EGFR, NOTE_DIALYSIS],
)
def test_confirmed_renal_impairment_is_parsed(note):
    status = rg.parse_renal_status([note])
    assert status.level == "impaired", status


def test_ruled_out_ckd_is_suspected_not_impaired():
    """`r/o CKD` 는 rule-out — 의심이지 확진이 아니다.

    확진으로 읽으면 26건이 전부 경고가 되고, 경고가 흔해지면 GFR 13 짜리
    진짜 경고가 묻힌다. 그렇다고 "해당 없음"으로 읽어서도 안 된다.
    """
    status = rg.parse_renal_status([NOTE_RO_CKD])
    assert status.level == "suspected", status
    assert "r/o" in status.evidence.lower()


@pytest.mark.parametrize("note", [NOTE_HEART_FAILURE, NOTE_KIDNEY_WATER, NOTE_NO_RENAL])
def test_non_renal_notes_are_undetermined(note):
    """신기능 지표가 없는 노트는 "정상"이 아니라 "확인 못 함"이다."""
    status = rg.parse_renal_status([note])
    assert status.level == "undetermined", status


def test_no_notes_at_all_is_undetermined():
    assert rg.parse_renal_status([]).level == "undetermined"
    assert rg.parse_renal_status(None).level == "undetermined"


def test_confirmed_beats_suspected_within_one_patient():
    status = rg.parse_renal_status([NOTE_RO_CKD, NOTE_GFR13])
    assert status.level == "impaired"


def test_high_gfr_alone_does_not_declare_normal():
    """단일 GFR 90 은 신기능 정상을 확정하지 않는다(시점·추세를 모른다)."""
    assert rg.parse_renal_status(["eGFR 90"]).level == "undetermined"


# --- 2. 약물 표 ---------------------------------------------------------------


def test_metformin_products_match_the_table():
    assert rg.match_renal_cleared_drug(DRUG_METFORMIN) is not None
    assert rg.match_renal_cleared_drug("메트폴엠정(메트포르민염산염)_(0.5g/1정)") is not None


def test_drug_outside_the_table_does_not_match():
    assert rg.match_renal_cleared_drug(DRUG_NOT_IN_TABLE) is None


def test_memotin_matches_memantine_via_reimbursement_criteria_token():
    """`메모틴정10mg` — 예전에는 "알면서 비운 자리"였다. 더 이상 아니다.

    2026-08-31 실측으로 세 증거를 확인했다(전부 라이브 그래프,
    `prescription_masters.693901500.canonical_name` 도 동일):

    1. 처방명이 급여기준을 그대로 담고 있다: `메모틴정10mg(MMSE20점이하,
       GDS 4-7점)`. 한국 급여기준에서 MMSE 20 이하 + GDS 4-7 은 메만틴
       기준이다(도네페질은 MMSE 10-26).
    2. 같은 그래프에 같은 10mg 용량의, 성분이 명시된 메만틴 제제가 있다:
       `디멘틴정_(메만틴염산염/ 10mg/1정)`(693901500 과 다른 코드
       661900170). `메만시아정10mg(메만틴염산염)`·`영일메만틴정(메만틴염산염)`
       ·`만티니정(메만틴염산염)` 도 전부 10mg 짜리 형제 제품이다.
    3. 이 데이터셋의 도네페질 제제는 전부 성분을 괄호로 명시한다
       (`알로페질정5mg(도네페질염산염)`, `환인도네페질정23밀리그램
       (도네페질염산염수화물)`) — 메모틴이 무표기 도네페질일 가능성은 낮다.

    이 셋은 약물 데이터베이스의 직접 진술이 아니라 급여기준 + 동일 용량
    형제 제품에서의 추론이다. 그 강도 그대로 `renal_gate.py` 표 주석에도
    적어 둔다.
    """
    drug = rg.match_renal_cleared_drug("메모틴정10mg(MMSE20점이하, GDS 4-7점)")
    assert drug is not None
    assert drug.ingredient == "memantine"


def test_table_is_not_empty_and_covers_observed_products():
    """표가 비면 관문은 영원히 clear 만 낸다 — 죽은 검사가 된다.

    아래 처방명은 전부 라이브 그래프 order_lines 의 실제 문자열이다.
    """
    observed = [
        "다이아벡스정500mg",
        "자누메트정50/500mg",
        "메만시아정10mg(메만틴염산염)_(10mg/1정)",
        "레티람정500밀리그램(레비티라세탐)_(0.5g/1정)",
        "프로카반캡슐75mg(프레가발린)_(75mg/1캡슐)",
        "구주스피로닥톤정",
        "아펜정(아세클로페낙)_(0.1g/1정)",
        "디고신정",
        "겐타프로주사(겐타마이신황산염)_(80mg/2mL)",
        "크라비트정500밀리그람(레보플록사신)_(0.5g/1정)",
        "휴온스시메티딘정200mg",
    ]
    assert len(rg.RENAL_CLEARED_DRUGS) >= 10
    unmatched = [n for n in observed if rg.match_renal_cleared_drug(n) is None]
    assert unmatched == []


# --- 3. 세 결과가 서로 무너지지 않는다 ---------------------------------------


def test_the_real_case_warns():
    """VISIT_530472595 — CKD 노트 환자에게 실제로 나간 메트포르민."""
    result = rg.evaluate_renal_gate(
        notes=[NOTE_DM_CKD], items=[_item(1, DRUG_METFORMIN)]
    )
    assert result.status == "warn"
    assert result.items[0].outcome == "warn"
    assert result.items[0].ingredient == "metformin"


def test_unknown_never_renders_as_clear():
    """신기능을 못 읽었는데 약은 표 안 — clear 가 아니라 unknown 이다."""
    result = rg.evaluate_renal_gate(
        notes=[NOTE_NO_RENAL], items=[_item(1, DRUG_METFORMIN)]
    )
    assert result.status == "unknown"
    assert result.items[0].outcome == "unknown"


def test_ruled_out_with_table_drug_is_unknown_not_warn():
    result = rg.evaluate_renal_gate(
        notes=[NOTE_RO_CKD], items=[_item(1, DRUG_METFORMIN)]
    )
    assert result.status == "unknown"


def test_drug_outside_table_is_clear_even_with_impairment():
    """"확인함·해당없음" — 신기능은 나빠도 이 약은 표 밖이다."""
    result = rg.evaluate_renal_gate(
        notes=[NOTE_GFR13], items=[_item(1, DRUG_NOT_IN_TABLE, code="642202450")]
    )
    assert result.status == "clear"
    assert result.items[0].outcome == "clear"


def test_note_fetch_failure_is_unknown_not_clear():
    result = rg.evaluate_renal_gate(notes=[], items=[_item(1, DRUG_METFORMIN)])
    assert result.status == "unknown"


def test_gate_status_is_the_worst_item():
    result = rg.evaluate_renal_gate(
        notes=[NOTE_GFR13],
        items=[
            _item(1, DRUG_NOT_IN_TABLE, code="642202450"),
            _item(2, DRUG_METFORMIN),
        ],
    )
    assert [i.outcome for i in result.items] == ["clear", "warn"]
    assert result.status == "warn"


def test_placeholder_item_is_unknown_not_clear():
    """플레이스홀더는 `clear` 가 아니라 `unknown` 이다.

    경고하지 않는 것과 `clear` 를 내는 것은 다르다. 이 항목의 evidence 는
    "대조할 약이 없습니다" 라고 정확히 말하는데, 예전에는 outcome 이
    `clear` 였다 — 화면에서 "확인했고 해당 없음" 으로 읽힌다.

    이 파일의 다른 자리는 전부 그 구분을 지킨다: 노트를 못 읽으면
    `unknown`(test_note_fetch_failure_is_unknown_not_clear), 판정할 항목이
    아예 없으면 `unknown`. **대조 불가를 `clear` 로 내지 않는다**는 것이
    이 부품의 원칙이고, 플레이스홀더만 그 원칙 밖에 있었다.

    설계 §3.2 이후 "이 순위에는 후보가 없다" 는 항목은 더 이상 만들어지지
    않는다(응답이 후보 수만큼만 길다). 그래도 이 경로는 죽지 않았다 —
    **처방명은 있는데 처방코드가 없는 후보**가 남아 있고, 그 항목의 코드가
    `ranking.MISSING_CODE` 다. 성분을 대조할 수 없으니 `clear` 가 아니다.
    """
    from ranking import MISSING_CODE

    result = rg.evaluate_renal_gate(
        notes=[NOTE_GFR13],
        items=[_item(1, "코드 없는 후보", code=MISSING_CODE)],
    )
    assert result.items[0].outcome == "unknown"
    assert "추천 항목" in result.items[0].evidence


def test_all_placeholder_slate_does_not_report_clear():
    """전 항목이 대조 불가면 최상위도 `clear` 가 아니다.

    `status` 는 항목 중 최고 심각도다. 플레이스홀더가 `clear` 였을 때는
    대조하지 못한 응답 전체가 `clear` 로 나갔다 — GFR 13 환자에게 "확인해
    보니 해당 없음" 으로 보이는 상태다.
    """
    from ranking import MISSING_CODE

    result = rg.evaluate_renal_gate(
        notes=[NOTE_GFR13],
        items=[_item(i, f"코드 없는 후보{i}", code=MISSING_CODE) for i in (1, 2, 3)],
    )
    assert result.renalStatus == "impaired"
    assert result.status == "unknown"


def test_result_dict_carries_all_three_axes():
    result = rg.evaluate_renal_gate(
        notes=[NOTE_GFR13], items=[_item(1, DRUG_METFORMIN)]
    )
    d = result.to_dict()
    assert d["status"] == "warn"
    assert d["renalStatus"] == "impaired"
    assert "GFR 13" in d["renalEvidence"]
    assert d["items"][0]["outcome"] == "warn"


# --- 4. 배선 -----------------------------------------------------------------


def test_response_model_has_renal_gate_field():
    import prescription_api

    assert "renalGate" in prescription_api.PrescriptionRecommendResponse.model_fields


def test_safe_renal_gate_swallows_exceptions(monkeypatch):
    """GC-4. 관문이 터져도 본 응답은 성공하고, 결과는 unknown 이다."""
    import prescription_api

    def boom(**kwargs):
        raise RuntimeError("관문 폭발")

    monkeypatch.setattr(prescription_api, "evaluate_renal_gate", boom)
    result = prescription_api._safe_renal_gate(notes=[], items=[])

    assert result["status"] == "unknown"
    assert "RuntimeError" in (result["undeterminedReason"] or "")


def test_note_fetch_unwraps_object_rows(monkeypatch):
    """AQL 이 스칼라를 돌려주면 노트가 조용히 사라진다 — 실제로 그랬다.

    `run_graph_qa._aql_rows` 는 커서를 `[dict(x) for x in cur]` 로 접는다.
    `RETURN TO_STRING(...)` 처럼 문자열 행을 내면 `dict("...")` 가 ValueError 를
    던지고, 그 예외는 ArangoError 가 아니라서 `_aql_rows` 의 except 를 통과해
    조회 전체가 빈 리스트가 된다. 2026-08-31 라이브 실행에서 실제로 그렇게
    됐고, 관문은 fail-closed 덕에 조용히 clear 가 아니라 unknown 을 냈다.
    그래도 노트를 읽지 못한 것은 결함이므로 여기서 행 모양을 고정한다.
    """
    import run_graph_qa
    import run_prescription_agent as rpa

    monkeypatch.setattr(run_graph_qa, "load_arango_config", lambda: {})
    monkeypatch.setattr(run_graph_qa, "connect_arango", lambda cfg: object())
    monkeypatch.setattr(
        run_graph_qa,
        "_aql_rows",
        lambda db, aql, bind: [{"note": NOTE_DM_CKD}, {"note": "   "}, {"note": None}],
    )

    assert "RETURN {" in rpa._SPECIAL_NOTES_AQL
    assert rpa.fetch_special_notes_from_arango("530472595") == [NOTE_DM_CKD]


def test_recommend_wires_renal_gate(monkeypatch):
    """recommend() 가 Arango 노트를 실제로 읽어 관문에 넘긴다."""
    import prescription_api as pa

    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setattr(
        pa, "fetch_special_notes_from_arango", lambda pid: [NOTE_DM_CKD]
    )

    req = pa.PrescriptionRecommendRequest(
        patient_id="530472595",
        symptoms="당뇨 추적",
        history="",
        top_rx=[{"처방명": DRUG_METFORMIN, "처방코드": "641600390"}],
        fetch_top_rx_from_arango=False,
        fetch_cohort_rx_from_arango=False,
    )
    resp = pa.recommend(req, x_prescription_eval_trace=None)

    assert resp.renalGate["status"] == "warn"
    assert resp.renalGate["renalStatus"] == "impaired"
