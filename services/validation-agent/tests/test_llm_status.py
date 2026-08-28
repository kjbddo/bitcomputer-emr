import os

from app import agent, tools
from app.agent import run_validation_agent
from app.models import ValidationAgentRequest


def _request() -> ValidationAgentRequest:
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[],
    )


def _passing_request() -> ValidationAgentRequest:
    """overallStatus 가 "PASS" 로 떨어지는 요청. 저장 상병과 저장 처방이 모두
    있어야 prescription_validator 가 "APPROPRIATE" 를 돌려주고(그래야
    "INSUFFICIENT_DATA" 체크가 안 생겨 NEEDS_REVIEW 로 빠지지 않는다), X-ray
    추론이 없어야 disease_validator 가 "MATCH" 로 판정한다."""
    return ValidationAgentRequest(
        historyId=1,
        symptoms="기침",
        savedDiseases=[{"code": "J00", "name": "감기"}],
        savedPrescriptions=[{"code": "P1", "name": "진해거담제"}],
    )


class _FakeLLM:
    """`_create_llm()` 대신 쓰는 대역. 실제 게이트웨이 네트워크 호출 없이
    보조 호출(PubMed 쿼리 생성/요약)이 실제로 LLM 경로를 타는 상황을
    재현한다(리뷰 finding 5) — 기존 세 테스트는 모두 `_create_llm` 을 `None`
    으로 고정해 두어서, "real" 경로인데도 보조 호출은 늘 폴백만 탔다."""

    def __init__(self, summary_text="PubMed 초록에 따르면 기침 관련 대증치료가 보고되었다 (PMID: 111)."):
        self.summary_text = summary_text

    def invoke(self, messages):
        prompt = str(messages[-1].content)
        if "PubMed ESearch" in prompt:
            content = '{"queries": ["cough treatment guideline"]}'
        else:
            content = self.summary_text

        class _Response:
            def __init__(self, content: str) -> None:
                self.content = content

        return _Response(content)


def _fake_pubmed_articles(_payload=None):
    """`pubmed_loader.invoke` 대역이 돌려줄 값. 실제 PubMed 네트워크 호출 없이
    근거 1건을 결정론적으로 돌려준다."""
    return {
        "status": "LOADED",
        "evidence": ["PubMed에서 1건의 근거 후보를 조회했습니다."],
        "articles": [
            {
                "pmid": "111",
                "title": "Cough treatment guideline",
                "source": "Test Journal",
                "pubdate": "2024",
                "abstract": "Cough treatment abstract.",
                "abstractSnippet": "Cough treatment abstract.",
            }
        ],
    }


class _FakePubmedLoader:
    """`agent.pubmed_loader` 를 통째로 대체하는 대역.

    `pubmed_loader` 는 pydantic 기반 `StructuredTool` 이라 인스턴스의 `invoke`
    속성을 직접 monkeypatch 할 수 없다(필드가 아니라서 `ValueError` 가 난다).
    대신 `agent` 모듈이 바라보는 이름 자체를 이 대역으로 바꿔치기한다.
    """

    def invoke(self, payload=None):
        return _fake_pubmed_articles(payload)


def test_stub_provider_reports_stub(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    assert response.llmStatus == "stub"


def test_no_gateway_configured_reports_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    response = run_validation_agent(_request())
    assert response.llmStatus == "fallback"


def test_fallback_trace_entries_are_marked(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    response = run_validation_agent(_request())
    assert response.reasoningTrace, "트레이스가 비어 있으면 이 테스트가 무의미하다"
    # 폴백으로 결정된 스텝은 트레이스만 보고 구분 가능해야 한다(spec §6.3).
    # "rule" 은 결정 루프 지원 없이 항상 실행되는 규칙 기반 후처리 전용 값이며
    # (리뷰 finding 2), 게이트웨이가 없는 이 시나리오에서는 "llm" 이 단 하나도
    # 나오지 않아야 한다는 것이 실제로 의미 있는 신호다.
    assert all(e["source"] in {"fallback", "rule"} for e in response.reasoningTrace)
    assert "llm" not in {e["source"] for e in response.reasoningTrace}  # 실제 신호


def test_trace_entries_always_carry_source(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    for entry in response.reasoningTrace:
        assert "source" in entry, "source 가 없으면 출처를 구분할 수 없다"


def _sequenced_llm_decision(sequence):
    """`_llm_tool_decision` 을 대신할 결정론적 대역. 게이트웨이 네트워크 호출 없이
    "이번 반복은 LLM 이 실제로 결정했다" 는 상황을 재현한다."""
    remaining = iter(sequence)

    def fake(state, reasoning_trace, pubmed_queries, iteration):
        return next(remaining, None)

    return fake


def test_llm_decision_reports_real_and_marks_trace_llm(monkeypatch):
    # "real" 경로에는 이 태스크 이전까지 실패할 수 있는 테스트가 없었다(리뷰 finding 3).
    # M1(agent.py:261, "_source"="llm" -> "fallback")과 M2(agent.py:222,
    # "source": source -> "source": "fallback") 모두 이 테스트로 잡혀야 한다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    # 결정 자체는 대역으로 통제하고, 보조 호출(쿼리 생성/요약)은 항상 폴백하도록
    # 고정해 이 테스트가 실제 네트워크에 의존하지 않게 한다.
    monkeypatch.setattr(agent, "_create_llm", lambda: None)
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}},
            {"thought": "상병 검증", "action": "Disease Validator", "actionInput": {}},
            {"thought": "처방 검증", "action": "Prescription Validator", "actionInput": {}},
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_request())

    assert response.llmStatus == "real"
    disease_entries = [e for e in response.reasoningTrace if e["action"] == "Disease Validator"]
    assert disease_entries, "Disease Validator 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] == "llm" for e in disease_entries)


def test_mixed_llm_and_fallback_decisions_produce_mixed_trace(monkeypatch):
    # LLM 이 한 반복에서는 성공하고 이후에는 실패(None)하는 경우, 트레이스는
    # 반복별로 실제 출처를 구분해서 보여줘야 한다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)

    calls = {"n": 0}

    def fake_llm_tool_decision(state, reasoning_trace, pubmed_queries, iteration):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}}
        return None  # 이후 반복은 LLM 결정 실패 -> 휴리스틱 폴백으로 떨어져야 한다

    monkeypatch.setattr(agent, "_llm_tool_decision", fake_llm_tool_decision)

    response = run_validation_agent(_request())

    sources = {e["source"] for e in response.reasoningTrace}
    assert "llm" in sources, "첫 반복의 llm 소스가 트레이스에 남아야 한다"
    assert "fallback" in sources, "이후 반복의 폴백 소스도 트레이스에 남아야 한다"


def test_llm_decisions_with_failed_auxiliary_calls_do_not_mark_pubmed_as_llm(monkeypatch):
    # 리뷰 finding 1 커버리지: 도구 선택은 전부 LLM 이 했지만(all decisions "llm"),
    # 보조 호출(PubMed 쿼리 생성/요약)은 실패하는 시나리오. 이전에는
    # Pubmed Loader 트레이스 항목이 "이 스텝을 촉발한 결정"의 출처를 그대로
    # 물려받아 "llm" 로 찍혔다 — 실제로 쓰인 검색어는 하드코딩된 사전에서
    # 나왔는데도. llmStatus 자체는 (브리프가 지정한, 이번 태스크에서 건드리지
    # 않는) "결정 하나라도 llm 이면 real" 낙관 규칙 때문에 "real" 로 남을 수
    # 있다 — 그래서 이 테스트는 최상위 llmStatus 가 아니라, 실제로 거짓을 말할
    # 수 있었던 세부 신호(Pubmed Loader 트레이스의 source)를 검증한다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)  # 보조 호출은 전부 실패/폴백
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}},
            {"thought": "상병 검증", "action": "Disease Validator", "actionInput": {}},
            {"thought": "처방 검증", "action": "Prescription Validator", "actionInput": {}},
            {"thought": "문헌 근거 확보", "action": "Pubmed Loader", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_request())

    pubmed_entries = [e for e in response.reasoningTrace if e["action"] == "Pubmed Loader"]
    assert pubmed_entries, "Pubmed Loader 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] != "llm" for e in pubmed_entries), (
        "쿼리 생성이 실패해 하드코딩된 사전으로 대체됐다면, "
        "이 스텝을 촉발한 결정이 llm 이었더라도 llm 이라고 주장하면 안 된다"
    )


def test_successful_llm_run_has_no_fallback_trace_entries(monkeypatch):
    # 리뷰 finding 3: agent.py:130, 150 의 "rule" 마킹을 "fallback" 으로 되돌려도
    # (뮤테이션 M5) 기존 스위트는 그대로 통과했다 — `test_fallback_trace_entries_are_marked`
    # 는 "fallback" 과 "rule" 을 한 집합으로 받아들여 둘을 구분하지 못하고, 흠 없는
    # 요청이 fallback 을 전혀 만들지 않는다는 것을 단언하는 테스트가 없었기 때문이다.
    # 이 테스트는 결정 루프가 매 반복 LLM 로 성공하고(=llm), 루프 밖 후처리
    # (PASS 후 PubMed 보강, 후보 없을 때의 Prescription Finder)가 "rule" 로
    # 찍히는 두 지점을 모두 거치도록 시나리오를 구성한다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}},
            {"thought": "상병 검증", "action": "Disease Validator", "actionInput": {}},
            {"thought": "처방 검증", "action": "Prescription Validator", "actionInput": {}},
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_passing_request())

    assert response.overallStatus == "PASS", "이 테스트는 PASS 후처리(agent.py:130)를 거쳐야 의미가 있다"
    assert not state_has_fallback(response), "흠 없는 LLM 실행에서는 fallback 소스가 하나도 없어야 한다"
    assert any(e["source"] == "rule" for e in response.reasoningTrace), (
        "루프 밖 후처리(PubMed 보강/Prescription Finder)가 rule 로 찍혀 있어야 "
        "M5 뮤테이션(rule -> fallback)이 이 테스트로 잡힌다"
    )


def state_has_fallback(response) -> bool:
    return any(e["source"] == "fallback" for e in response.reasoningTrace)


def test_pubmed_summary_label_marks_rule_based_when_llm_unavailable(monkeypatch):
    # 리뷰 finding 4: agent.py:162 를 무조건 "PubMed 근거 요약" 으로 되돌려도
    # (뮤테이션 M7) 기존 스위트는 그대로 통과했다 — checks[] 의 PUBMED_EVIDENCE
    # 메시지에 "(규칙 기반)" 라벨이 실제로 붙는지 검증하는 테스트가 없었기 때문이다.
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)  # 요약은 반드시 폴백을 탄다
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {
                "thought": "문헌 근거 확보",
                "action": "Pubmed Loader",
                "actionInput": {"query": "cough treatment guideline"},
            },
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_passing_request())

    pubmed_checks = [c for c in response.checks if c.get("type") == "PUBMED_EVIDENCE"]
    assert pubmed_checks, "PubMed 근거 요약 체크가 있어야 이 테스트가 의미가 있다"
    assert "(규칙 기반)" in pubmed_checks[0]["message"]


def test_pubmed_summary_label_omits_rule_based_marker_when_llm_succeeds(monkeypatch):
    # finding 4 의 반대 방향: 요약이 실제로 LLM 에서 나왔다면 "(규칙 기반)" 이
    # 붙으면 안 된다. FakeLLM 으로 요약 호출이 실제로 "llm" 경로를 타게 한다
    # (리뷰 finding 5 — 기존 테스트는 전부 _create_llm 을 None 으로 고정해
    # 이 경로를 한 번도 실행하지 않았다).
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {
                "thought": "문헌 근거 확보",
                "action": "Pubmed Loader",
                "actionInput": {"query": "cough treatment guideline"},
            },
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_passing_request())

    pubmed_checks = [c for c in response.checks if c.get("type") == "PUBMED_EVIDENCE"]
    assert pubmed_checks, "PubMed 근거 요약 체크가 있어야 이 테스트가 의미가 있다"
    assert "(규칙 기반)" not in pubmed_checks[0]["message"]


def test_second_pubmed_call_downgrades_to_fallback_when_llm_query_is_deduped(monkeypatch):
    # 리뷰 finding 2: query_source 가 배치(호출) 단위였다. 첫 번째 질의 없는
    # Pubmed Loader 호출에서 LLM 이 생성한 질의문이 검색에 쓰이면 트레이스는
    # 정당하게 "llm" 이 된다. 하지만 같은 세션의 두 번째 질의 없는 호출에서는
    # _build_pubmed_queries 가 매번 같은 LLM 질의문을 다시 생성하는데, 그
    # 질의문은 이미 pubmed_queries 에 있어 건너뛰어지고 하드코딩된
    # KOREAN_PUBMED_TERMS 사전 빌더 질의문("cough treatment")이 대신 쓰인다.
    # 이 경우 트레이스는 "llm" 이 아니라 "fallback" 이어야 한다(per-query 다운그레이드).
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "문헌 근거 확보1", "action": "Pubmed Loader", "actionInput": {}},
            {"thought": "문헌 근거 확보2", "action": "Pubmed Loader", "actionInput": {}},
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_passing_request())

    pubmed_entries = [e for e in response.reasoningTrace if e["action"] == "Pubmed Loader"]
    assert len(pubmed_entries) == 2, "질의 없는 Pubmed Loader 결정 두 번이 각각 트레이스에 남아야 한다"
    assert pubmed_entries[0]["source"] == "llm"
    assert pubmed_entries[0]["actionInput"]["query"] == "cough treatment guideline"
    assert pubmed_entries[1]["source"] == "fallback", (
        "두 번째 호출은 LLM 질의문이 중복 제거로 빠지고 사전 빌더 질의문이 쓰였으므로 "
        "이 스텝을 촉발한 결정이 llm 이었더라도 fallback 으로 다운그레이드돼야 한다"
    )
    assert pubmed_entries[1]["actionInput"]["query"] == "cough treatment"


def test_finalize_decision_leaves_trace_entry(monkeypatch):
    # Finding A (GC-2): 모델이 1회차에 FINALIZE 를 결정하면 루프가
    # `_execute_decided_tool` 을 부르기 전에 break 해서 트레이스에 아무 흔적도
    # 남지 않았다. llmStatus 는 실제로 LLM 이 결정했으므로 정확히 "real" 이지만,
    # 트레이스는 모델 관여를 전혀 보여주지 못해 두 값을 같이 보는 소비자가
    # 앞뒤를 맞출 수 없었다(리뷰 H1 — "더 확인할 것 없음" 은 흔한 정상 종료다).
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "더 확인할 것이 없다", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_request())

    assert response.llmStatus == "real"
    finalize_entries = [e for e in response.reasoningTrace if e["action"] == "FINALIZE"]
    assert finalize_entries, "FINALIZE 결정도 트레이스에 남아야 한다(GC-2) — 아니면 llmStatus=real 이 근거 없는 주장이 된다"
    assert finalize_entries[0]["source"] == "llm"
    assert finalize_entries[0]["observation"] == {"status": "FINALIZED"}


class _FakeHttpResponse:
    def __init__(self, json_body):
        self._json_body = json_body

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_body


class _FakeHttpxClient:
    """`httpx.Client` 컨텍스트 매니저 대역. `tools.prescription_finder` 가 실제
    네트워크 호출 없이 정해진 JSON 응답을 받도록 한다."""

    def __init__(self, json_body):
        self._json_body = json_body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        return _FakeHttpResponse(self._json_body)


def test_tools_prescription_finder_forwards_upstream_llm_status(monkeypatch):
    """`agent.py` 쪽 테스트는 `agent.prescription_finder` 전체를 대역으로
    바꿔치기해서 검증하므로 `tools.py` 자신의 딕셔너리 구성 로직은 우회된다.
    `prescription_api` 가 실제로 응답에 실은 `llmStatus` 가 `tools.py` 의
    `recommendationLlmStatus` 로 정확히 전달되는지는 여기서 직접 확인해야 한다.
    """
    monkeypatch.setattr(
        tools.httpx,
        "Client",
        lambda *args, **kwargs: _FakeHttpxClient({"prescriptions": [], "llmStatus": "stub"}),
    )

    result = tools.prescription_finder.invoke({
        "patient_id": "1",
        "diseases": [],
        "symptoms": "",
    })

    assert result["recommendationLlmStatus"] == "stub"


def test_tools_prescription_finder_failure_reports_fallback_llm_status(monkeypatch):
    """처방 RAG 호출 자체가 실패하면 모델은 이 스텝에 관여하지 않았다 —
    상류가 뭐라고 했을지와 무관하게 fallback 이어야 한다."""

    def _raise(*args, **kwargs):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(tools.httpx, "Client", _raise)

    result = tools.prescription_finder.invoke({
        "patient_id": "1",
        "diseases": [],
        "symptoms": "",
    })

    assert result["recommendationLlmStatus"] == "fallback"


class _FakePrescriptionFinder:
    """`agent.prescription_finder` 를 통째로 대체하는 대역.

    `prescription_finder` 도 `_FakePubmedLoader` 와 마찬가지로 pydantic 기반
    `StructuredTool` 이라 인스턴스의 `invoke` 속성을 직접 monkeypatch 할 수
    없다. 대신 `agent` 모듈이 바라보는 이름 자체를 이 대역으로 바꿔치기한다.
    """

    def __init__(self, llm_status):
        self.llm_status = llm_status

    def invoke(self, payload=None):
        return {
            "status": "LOADED",
            "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
            "candidatePrescriptions": [
                {
                    "id": 1,
                    "rank": 1,
                    "prescription_code": "C1",
                    "prescription_name": "약1",
                    "reason": "",
                    "confidence_score": 0.9,
                }
            ],
            # 처방 RAG 자신이 모델을 썼는지 — Prescription Finder 트레이스 항목의
            # source 판정에만 쓰인다(task 11 §Step 21-22).
            "recommendationLlmStatus": self.llm_status,
        }


def _install_prescription_finder(monkeypatch, llm_status):
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder(llm_status))


def _install_llm_decisions(monkeypatch):
    """결정 루프의 모든 반복이 LLM 결정이고, Prescription Finder 를 반드시
    거치도록 시퀀스를 구성하는 대역. 처방 RAG 자신의 출처(stub/fallback)가
    최상위 llmStatus 를 오염시키지 않는지 확인하려면, 결정 자체는 전부 LLM 이
    내렸다는 전제가 필요하다(그래야 llmStatus="real" 이 다른 이유로 나온 게
    아니라는 것이 분명해진다).
    """
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "x-ray 로드", "action": "X-ray Result Loader", "actionInput": {}},
            {"thought": "상병 검증", "action": "Disease Validator", "actionInput": {}},
            {"thought": "처방 검증", "action": "Prescription Validator", "actionInput": {}},
            {"thought": "처방 후보 조회", "action": "Prescription Finder", "actionInput": {}},
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )


def test_prescription_finder_trace_marks_stub_recommendation(monkeypatch):
    """처방 RAG 가 스텁 응답을 돌려주면 그 스텝의 source 는 llm 이 될 수 없다.

    결정 자체는 LLM 이 했더라도, 이 스텝의 페이로드는 스텁에서 나왔다.
    source 의 선언된 의미가 "이 스텝의 페이로드가 어디서 왔나"이므로 여기가 맞다.
    """
    _install_llm_decisions(monkeypatch)
    _install_prescription_finder(monkeypatch, llm_status="stub")

    response = run_validation_agent(_request())

    finder = [e for e in response.reasoningTrace if e["action"] == "Prescription Finder"]
    assert finder, "Prescription Finder 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] != "llm" for e in finder)


def test_prescription_finder_stub_does_not_flip_top_level_status(monkeypatch):
    """스텝 출처가 최상위 llmStatus 를 오염시키면 안 된다(Task 6 회귀 방지).

    보조 호출의 결과를 결정 소스에 섞었다가, 결정이 전부 스텁인데 llmStatus 가
    "real" 로 나오는 결함을 만든 적이 있다. 방향을 반대로도 확인한다 —
    처방 RAG 가 스텁이라고 해서 LLM 이 내린 결정이 지워지지도 않아야 한다.
    """
    _install_llm_decisions(monkeypatch)
    _install_prescription_finder(monkeypatch, llm_status="stub")

    response = run_validation_agent(_request())

    assert response.llmStatus == "real"


def test_prescription_finder_real_payload_does_not_promote_stub_decisions(monkeypatch):
    """Task 6 결함을 정확한 형태로 재현한다: 결정이 전부 스텁인데 처방 RAG
    보조 호출 하나가 "real" 을 보고했다는 이유로 최상위 llmStatus 가 real 로
    뒤바뀌면 안 된다.

    바로 위 테스트(llm 결정 + stub 페이로드)는 `_resolve_llm_status` 가 "llm 이
    하나라도 있으면 real" 을 최우선으로 보기 때문에, 이미 llm 결정이 있는
    상태에서는 무엇을 더 섞어 넣어도 결과가 바뀌지 않는다 — decision_sources
    오염이 실제로 결과를 뒤집을 수 있는 유일한 방향은 이쪽(전부 스텁인 상태에
    real/llm 값이 섞여 들어오는 경우)이다. LLM_PROVIDER=stub 이면 결정 시퀀스가
    Prescription Finder 를 직접 고르지 않으므로, 이 호출은 루프 밖 후처리
    경로(§Step 22 의 "결정 루프 밖에서 항상 실행되는 후처리")를 통해서만 실행된다.
    """
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    _install_prescription_finder(monkeypatch, llm_status="real")

    response = run_validation_agent(_request())

    assert response.llmStatus == "stub"


def test_hallucinated_action_produces_trace_entry(monkeypatch):
    # Finding B (GC-2): `_execute_decided_tool` 은 인식되는 액션마다
    # `if action == ...: return` 체인이고 terminal else 가 없어서, 모델이
    # 존재하지 않는 도구 이름을 결정하면 모든 분기를 통과해 아무것도 하지 않고
    # 리턴했다 — 트레이스도, observation 도, 로그도 없이 다음 반복으로 조용히
    # 넘어갔다(리뷰 H2).
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.setattr(agent, "_create_llm", lambda: None)
    monkeypatch.setattr(
        agent,
        "_llm_tool_decision",
        _sequenced_llm_decision([
            {"thought": "환각 도구 호출", "action": "Nonexistent Tool", "actionInput": {"foo": "bar"}},
            {"thought": "종료", "action": "FINALIZE", "actionInput": {}},
        ]),
    )

    response = run_validation_agent(_request())

    unknown_entries = [e for e in response.reasoningTrace if e["action"] == "Nonexistent Tool"]
    assert unknown_entries, "인식되지 않는 액션도 트레이스에 남아야 한다(GC-2) — 조용히 드롭하면 안 된다"
    assert unknown_entries[0]["source"] == "llm"
    assert unknown_entries[0]["observation"] == {
        "status": "UNKNOWN_ACTION",
        "evidence": ["Nonexistent Tool"],
    }
