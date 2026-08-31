import json
from types import SimpleNamespace

from llm_provider import (
    STUB_MARKER,
    resolve_provider,
    stub_certificate_response,
    stub_prescription_response,
)
from prescription_agent import parse_prescriptions_llm_response


def test_resolve_provider_defaults_to_real(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert resolve_provider() == "real"


def test_resolve_provider_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert resolve_provider() == "stub"


# 스텁의 입력은 조회가 확정한 slate 다(RankedCandidate.to_prompt_row 목록).
# 응답 길이가 slate 길이와 같아야 하므로(설계 §3.2) 스텁도 그 길이를 따른다.
_SLATE_2 = [
    {"rank": 1, "name": "아목시실린캡슐", "prescription_code": "A001", "confidence_score": 0.4},
    {"rank": 2, "name": "타이레놀정", "prescription_code": "B002", "confidence_score": None},
]
_SLATE_1 = [_SLATE_2[0]]


def test_stub_response_parses_with_real_parser():
    raw = stub_prescription_response(_SLATE_2)
    data = parse_prescriptions_llm_response(raw, expected_count=2)
    assert len(data["prescriptions"]) == 2
    assert [p["rank"] for p in data["prescriptions"]] == [1, 2]


def test_stub_response_length_follows_the_slate_not_a_fixed_three():
    """3건 고정으로 되돌리면 후보 2건일 때 파서가 정당하게 거부한다."""
    assert len(json.loads(stub_prescription_response(_SLATE_1))["prescriptions"]) == 1
    assert len(json.loads(stub_prescription_response(_SLATE_2))["prescriptions"]) == 2


def test_stub_response_uses_codes_from_input():
    data = json.loads(stub_prescription_response(_SLATE_1))
    assert data["prescriptions"][0]["prescription_code"] == "A001"


def test_stub_response_is_deterministic():
    assert stub_prescription_response(_SLATE_1) == stub_prescription_response(_SLATE_1)


def test_stub_response_for_an_empty_slate_is_empty():
    """빈손을 3건으로 채우지 않는다. 호출자는 애초에 여기까지 오지 않는다."""
    assert json.loads(stub_prescription_response([]))["prescriptions"] == []


def _certificate_req(**overrides):
    defaults = dict(
        diagnosis_kind="임상적 추정",
        purpose="사내 제출용",
        diseases=[SimpleNamespace(name="급성 위염"), SimpleNamespace(name="")],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_stub_certificate_response_contains_marker():
    text = stub_certificate_response(_certificate_req())
    assert STUB_MARKER in text


def test_stub_certificate_response_is_plain_string():
    text = stub_certificate_response(_certificate_req())
    assert isinstance(text, str)
    assert not hasattr(text, "content")


def test_stub_certificate_response_uses_disease_names():
    text = stub_certificate_response(_certificate_req())
    assert "급성 위염" in text


def test_stub_certificate_response_handles_dict_diseases():
    req = _certificate_req(diseases=[{"name": "감기"}])
    text = stub_certificate_response(req)
    assert "감기" in text


def test_stub_certificate_response_handles_empty_diseases():
    req = _certificate_req(diseases=[])
    text = stub_certificate_response(req)
    assert "상병명 미기재" in text


def test_stub_certificate_response_is_deterministic():
    req = _certificate_req()
    assert stub_certificate_response(req) == stub_certificate_response(req)
