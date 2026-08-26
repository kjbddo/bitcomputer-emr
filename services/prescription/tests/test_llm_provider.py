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


def test_stub_response_parses_with_real_parser():
    top_rx = [
        {"처방명": "아목시실린캡슐", "처방코드": "A001"},
        {"처방명": "타이레놀정", "처방코드": "B002"},
    ]
    raw = stub_prescription_response(top_rx)
    data = parse_prescriptions_llm_response(raw)
    assert len(data["prescriptions"]) == 3
    assert [p["rank"] for p in data["prescriptions"]] == [1, 2, 3]


def test_stub_response_uses_codes_from_input():
    top_rx = [{"처방명": "아목시실린캡슐", "처방코드": "A001"}]
    data = json.loads(stub_prescription_response(top_rx))
    assert data["prescriptions"][0]["prescription_code"] == "A001"


def test_stub_response_is_deterministic():
    top_rx = [{"처방명": "아목시실린캡슐", "처방코드": "A001"}]
    assert stub_prescription_response(top_rx) == stub_prescription_response(top_rx)


def test_stub_response_handles_empty_input():
    data = json.loads(stub_prescription_response([]))
    assert data["prescriptions"][0]["prescription_code"] == "미기재"


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
