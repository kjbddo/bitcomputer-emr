"""`llmStatus` 와 트레이스 스텝 `source` 의 계약.

ReAct 도구 선택 루프를 제거한 뒤(아키텍처 리뷰 §5) 이 두 값의 근거가 바뀌었다.

- 예전: `llmStatus` 는 **도구 이름을 고른 결정**의 출처에서 나왔다. "real" 은
  "모델이 도구 이름을 골랐다" 를 뜻했다.
- 지금: `llmStatus` 는 **응답 본문의 문장을 만든 모델 호출**에서만 나온다
  (`gateway.ModelCallLedger`). 남은 호출은 PubMed 질의 생성과 근거 요약 둘뿐이고,
  "real" 은 처음으로 "모델이 이 응답에 무언가를 썼다" 를 뜻한다.

이 파일이 고정하는 것은 그 경계다. 특히 **오염 금지** 규율 — 도구 실행 결과나
상류 서비스(`recommendationLlmStatus`)가 장부에 들어가면 안 된다 — 는 루프가
사라진 지금 오히려 더 중요하다. 신호가 둘뿐이라 오염 한 건의 무게가 크다.
"""
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
    """`create_llm()` 대신 쓰는 대역. 실제 게이트웨이 네트워크 호출 없이
    두 모델 호출(PubMed 질의 생성/요약)이 실제로 LLM 경로를 타는 상황을
    재현한다."""

    QUERY = "cough treatment guideline"

    def __init__(self, summary_text="PubMed 초록에 따르면 기침 관련 대증치료가 보고되었다 (PMID: 111)."):
        self.summary_text = summary_text

    def invoke(self, messages):
        prompt = str(messages[-1].content)
        if "PubMed ESearch" in prompt:
            content = '{"queries": ["%s"]}' % self.QUERY
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


class _EmptyForQueryPubmedLoader:
    """지정한 질의에만 0건을 돌려주는 대역.

    "모델 질의는 0건, 사전 빌더 질의가 성공" 이라는 실제 관측 상황(아키텍처
    리뷰 §5.3 의 컨테이너 로그)을 재현한다.
    """

    def __init__(self, empty_query: str) -> None:
        self.empty_query = empty_query
        self.queries: list[str] = []

    def invoke(self, payload=None):
        query = (payload or {}).get("query", "")
        self.queries.append(query)
        if query == self.empty_query:
            return {"status": "NO_RESULT", "evidence": [f"PubMed 검색 결과 없음: {query}"], "articles": []}
        return _fake_pubmed_articles(payload)


def _real_mode(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "real")
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://dummy-gateway.invalid")
    monkeypatch.delenv("VALIDATION_JOB_BUDGET_SECONDS", raising=False)


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
    # 게이트웨이가 없는 시나리오에서는 "llm" 이 단 하나도 나오지 않아야 한다.
    assert all(e["source"] in {"fallback", "rule"} for e in response.reasoningTrace)
    assert "llm" not in {e["source"] for e in response.reasoningTrace}  # 실제 신호


def test_trace_entries_always_carry_source(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    response = run_validation_agent(_request())
    for entry in response.reasoningTrace:
        assert "source" in entry, "source 가 없으면 출처를 구분할 수 없다"


# ---------------------------------------------------------------------------
# 모델이 실제로 쓴 것만 "llm" / "real" 이다
# ---------------------------------------------------------------------------


def test_model_generated_query_marks_trace_llm_and_status_real(monkeypatch):
    """모델이 질의를 만들었으면 그 스텝은 "llm" 이고 최상위는 "real" 이다.

    이것이 루프 제거 후 `llmStatus="real"` 이 가질 수 있는 유일하게 정직한
    의미다 — 옛 정의("모델이 도구 이름을 골랐다")와 달리, 여기서는 모델이
    실제로 검색어 문장을 썼다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    response = run_validation_agent(_request())

    assert response.llmStatus == "real"
    pubmed_entries = [e for e in response.reasoningTrace if e["action"] == "Pubmed Loader"]
    assert pubmed_entries and pubmed_entries[0]["source"] == "llm"
    assert pubmed_entries[0]["actionInput"]["query"] == _FakeLLM.QUERY


def test_trace_mixes_llm_and_rule_sources_in_one_run(monkeypatch):
    """한 실행 안에서 스텝별 출처가 갈린다.

    최상위 `llmStatus` 하나로 뭉뚱그리면 "모델이 무엇을 했고 무엇을 안 했는지"
    가 사라진다(spec §6.3 완료 조건 6). 도구 실행은 규칙, 검색어는 모델이다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    sources = {e["source"] for e in run_validation_agent(_request()).reasoningTrace}

    assert "llm" in sources, "모델이 만든 질의를 쓴 스텝이 있어야 한다"
    assert "rule" in sources, "결정론적으로 실행된 도구 스텝이 있어야 한다"


def test_failed_query_generation_never_marks_pubmed_step_llm(monkeypatch):
    """질의 생성이 실패해 하드코딩 사전으로 대체됐다면 "llm" 이라 주장하면 안 된다."""
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: None)  # 모델 호출 불가
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    response = run_validation_agent(_request())

    pubmed_entries = [e for e in response.reasoningTrace if e["action"] == "Pubmed Loader"]
    assert pubmed_entries, "Pubmed Loader 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] != "llm" for e in pubmed_entries)
    assert response.llmStatus == "fallback"


def test_builder_query_step_is_not_marked_llm_when_model_query_returned_nothing(monkeypatch):
    """스텝의 출처는 **이번에 실제로 쓰인 질의문** 기준이다.

    모델 질의가 0건을 내고 사전 빌더 질의가 성공한 경우(라이브 로그로 관측된
    실제 상황), 두 번째 스텝은 "llm" 이 아니다 — 그 검색어는 모델이 만들지
    않았다. 배치 단위로 판정하면 이 스텝까지 "llm" 이 찍힌다.
    """
    _real_mode(monkeypatch)
    loader = _EmptyForQueryPubmedLoader(empty_query=_FakeLLM.QUERY)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", loader)

    response = run_validation_agent(_passing_request())

    pubmed_entries = [e for e in response.reasoningTrace if e["action"] == "Pubmed Loader"]
    assert len(pubmed_entries) == 2, "0건 뒤 다음 질의로 넘어간 두 스텝이 남아야 한다"
    assert pubmed_entries[0]["source"] == "llm"
    assert pubmed_entries[0]["actionInput"]["query"] == _FakeLLM.QUERY
    assert pubmed_entries[1]["source"] == "rule", (
        "사전 빌더가 만든 검색어를 쓴 스텝을 llm 이라 표기하면 안 된다"
    )
    assert pubmed_entries[1]["actionInput"]["query"] == "cough treatment"
    # 질의 생성 호출 자체는 성공했으므로 최상위는 여전히 "real" 이다 —
    # 모델이 쓴 질의는 실제로 검색에 쓰였다(결과가 0건이었을 뿐).
    assert response.llmStatus == "real"


def test_successful_llm_run_has_no_fallback_trace_entries(monkeypatch):
    """흠 없는 실행에서 "fallback" 은 하나도 나오면 안 된다.

    "rule" 과 "fallback" 은 다른 말이다 — 앞은 "모델이 관여할 여지가 없는
    단계", 뒤는 "모델을 시도했는데 실패했다" 다. 둘을 한 집합으로 받아들이면
    실패 신호가 무의미해진다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("real"))

    response = run_validation_agent(_passing_request())

    assert response.overallStatus == "PASS"
    assert not any(e["source"] == "fallback" for e in response.reasoningTrace)
    assert any(e["source"] == "rule" for e in response.reasoningTrace)


# ---------------------------------------------------------------------------
# 요약 라벨 — 규칙 기반 조합을 모델이 쓴 것처럼 보이게 하지 않는다
# ---------------------------------------------------------------------------


def test_pubmed_summary_label_marks_rule_based_when_llm_unavailable(monkeypatch):
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: None)  # 요약은 반드시 폴백을 탄다
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    response = run_validation_agent(_passing_request())

    pubmed_checks = [c for c in response.checks if c.get("type") == "PUBMED_EVIDENCE"]
    assert pubmed_checks, "PubMed 근거 요약 체크가 있어야 이 테스트가 의미가 있다"
    assert "(규칙 기반)" in pubmed_checks[0]["message"]


def test_pubmed_summary_label_omits_rule_based_marker_when_llm_succeeds(monkeypatch):
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    response = run_validation_agent(_passing_request())

    pubmed_checks = [c for c in response.checks if c.get("type") == "PUBMED_EVIDENCE"]
    assert pubmed_checks, "PubMed 근거 요약 체크가 있어야 이 테스트가 의미가 있다"
    assert "(규칙 기반)" not in pubmed_checks[0]["message"]


def _pubmed_evidence_check(response):
    pubmed_checks = [c for c in response.checks if c.get("type") == "PUBMED_EVIDENCE"]
    assert pubmed_checks, "PubMed 근거 요약 체크가 있어야 이 테스트가 의미가 있다"
    return pubmed_checks[0]


def test_pubmed_check_message_carries_rule_based_summary_body(monkeypatch):
    """라벨만 남고 본문이 잘려나가는 회귀를 막는다.

    의료진이 화면에서 실제로 읽는 것은 요약 본문(PMID 인용 포함)이다 —
    라벨 유무만 보는 테스트로는 본문 삭제가 잡히지 않는다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: None)
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    response = run_validation_agent(_passing_request())

    message = _pubmed_evidence_check(response)["message"]
    assert "Cough treatment guideline (PMID 111)" in message
    assert "Cough treatment abstract." in message

    summary = response.validation["pubmedEvidenceSummary"]
    assert summary, "요약 본문이 비어 있으면 checks[] 메시지 검증이 무의미해진다"
    assert summary in message, "checks[] 메시지에 요약 본문이 그대로 실려야 한다"


def test_pubmed_check_message_carries_llm_summary_body(monkeypatch):
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())

    response = run_validation_agent(_passing_request())

    message = _pubmed_evidence_check(response)["message"]
    assert "PubMed 초록에 따르면 기침 관련 대증치료가 보고되었다 (PMID: 111)." in message

    summary = response.validation["pubmedEvidenceSummary"]
    assert summary, "요약 본문이 비어 있으면 checks[] 메시지 검증이 무의미해진다"
    assert summary in message, "checks[] 메시지에 요약 본문이 그대로 실려야 한다"


# ---------------------------------------------------------------------------
# tools.prescription_finder 자체의 계약
# ---------------------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, json_body):
        self._json_body = json_body

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_body


class _FakeHttpxClient:
    def __init__(self, json_body, captured):
        self._json_body = json_body
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, json=None):
        self._captured["url"] = url
        self._captured["payload"] = json
        return _FakeHttpResponse(self._json_body)


def _install_fake_httpx(monkeypatch, json_body, captured):
    def factory(timeout=None):
        captured["timeout"] = timeout
        return _FakeHttpxClient(json_body, captured)

    monkeypatch.setattr(tools.httpx, "Client", factory)


def test_tools_prescription_finder_forwards_upstream_llm_status(monkeypatch):
    captured: dict = {}
    _install_fake_httpx(monkeypatch, {"prescriptions": [], "llmStatus": "stub"}, captured)

    result = tools.prescription_finder.invoke({
        "patient_id": "1",
        "diseases": [],
        "symptoms": "",
    })

    assert result["recommendationLlmStatus"] == "stub"


def test_tools_prescription_finder_uses_configurable_timeout_matching_prescription_budget(monkeypatch):
    """호출자 타임아웃이 피호출자 총예산보다 짧으면, prescription-api 가 정상
    응답을 만들고 있는데도 이쪽이 먼저 포기해 "처방 RAG 호출 실패" 가 남는다."""
    captured: dict = {}
    monkeypatch.delenv("PRESCRIPTION_AGENT_TIMEOUT_SECONDS", raising=False)
    _install_fake_httpx(monkeypatch, {"prescriptions": []}, captured)

    tools.prescription_finder.invoke({"patient_id": "1", "diseases": [], "symptoms": ""})

    assert captured["timeout"] == 180.0


def test_tools_prescription_finder_timeout_reads_env(monkeypatch):
    captured: dict = {}
    monkeypatch.setenv("PRESCRIPTION_AGENT_TIMEOUT_SECONDS", "45")
    _install_fake_httpx(monkeypatch, {"prescriptions": []}, captured)

    tools.prescription_finder.invoke({"patient_id": "1", "diseases": [], "symptoms": ""})

    assert captured["timeout"] == 45.0


def test_tools_prescription_finder_failure_reports_fallback_llm_status(monkeypatch):
    def exploding(timeout=None):
        raise RuntimeError("연결 실패")

    monkeypatch.setattr(tools.httpx, "Client", exploding)

    result = tools.prescription_finder.invoke({
        "patient_id": "1",
        "diseases": [],
        "symptoms": "",
    })

    assert result["recommendationLlmStatus"] == "fallback"


# ---------------------------------------------------------------------------
# 오염 금지 — 상류 서비스의 출처가 이 서비스의 llmStatus 가 되면 안 된다
# ---------------------------------------------------------------------------


class _FakePrescriptionFinder:
    """`agent.prescription_finder` 를 통째로 대체하는 대역."""

    def __init__(self, llm_status):
        self.llm_status = llm_status

    def invoke(self, payload=None):
        return {
            "status": "LOADED",
            "evidence": ["기존 처방 RAG에서 참고 처방 후보를 조회했습니다."],
            "candidatePrescriptions": [
                {
                    "id": 1, "rank": 1, "prescription_code": "C1",
                    "prescription_name": "약1", "reason": "", "confidence_score": 0.9,
                }
            ],
            # 처방 RAG 자신이 모델을 썼는지 — Prescription Finder 트레이스 항목의
            # source 판정에만 쓰인다. 최상위 llmStatus 에 섞으면 Task 6 회귀다.
            "recommendationLlmStatus": self.llm_status,
        }


def test_prescription_finder_trace_marks_stub_recommendation(monkeypatch):
    """처방 RAG 가 스텁 응답을 돌려주면 그 스텝은 "규칙 기반" 이 아니라 "스텁" 이다.

    이 스텝을 실행한 것은 규칙이지만, 화면에 실려 가는 **데이터** 는 스텁에서
    왔다. 라이브에서 실제로 관측된 상태다(F-H3) — 그 사실이 트레이스에서
    사라지면 스텁 처방이 깨끗한 화면으로 의사에게 간다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("stub"))

    response = run_validation_agent(_request())

    finder = [e for e in response.reasoningTrace if e["action"] == "Prescription Finder"]
    assert finder, "Prescription Finder 스텝이 트레이스에 있어야 한다"
    assert finder[0]["source"] == "stub"


def test_prescription_finder_stub_does_not_flip_top_level_status(monkeypatch):
    """스텝 출처가 최상위 llmStatus 를 오염시키면 안 된다(Task 6 회귀 방지).

    방향을 반대로도 확인한다 — 처방 RAG 가 스텁이라고 해서 이 서비스가 실제로
    성사시킨 모델 호출이 지워지지도 않아야 한다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("stub"))

    assert run_validation_agent(_request()).llmStatus == "real"


def test_prescription_finder_real_payload_does_not_promote_failed_model_calls(monkeypatch):
    """Task 6 결함의 정확한 형태: 이 서비스의 모델 호출이 전부 실패했는데
    처방 RAG 보조 호출 하나가 "real" 을 보고했다는 이유로 최상위 llmStatus 가
    real 로 뒤바뀌면 안 된다."""
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: None)
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("real"))

    assert run_validation_agent(_request()).llmStatus == "fallback"


def test_prescription_finder_real_payload_never_marks_trace_llm(monkeypatch):
    """"승격 금지" 는 트레이스 자체로도 확인돼야 한다.

    `_downgrade_by_payload_source` 맨 위에 승격 분기
    (`if payload_status == "real": return "llm"`)를 끼워 넣어도 최상위
    llmStatus 만 보는 테스트는 통과한다. 이 스텝에는 이 서비스의 모델이
    아무것도 쓰지 않았으므로 "llm" 이 될 수 없다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _FakePrescriptionFinder("real"))

    response = run_validation_agent(_request())

    finder_entries = [e for e in response.reasoningTrace if e["action"] == "Prescription Finder"]
    assert finder_entries, "Prescription Finder 스텝이 트레이스에 있어야 한다"
    assert all(e["source"] != "llm" for e in finder_entries)
    assert finder_entries[0]["source"] == "rule"


class _RaisingPrescriptionFinder:
    def invoke(self, payload=None):
        raise RuntimeError("처방 RAG 연결 실패")


def test_prescription_finder_exception_fails_closed_not_rule(monkeypatch):
    """호출 자체가 예외를 던지면 observation 에 `recommendationLlmStatus` 키가
    아예 없다. `observation.get(...)` 이 돌려주는 `None` 을 관대하게 다루면
    실패한 호출이 정상 실행처럼 읽힌다.

    강등 목적지까지 고정한다 — "rule"(정상 실행) 로 남으면 실패가 화면에서
    사라진다.
    """
    _real_mode(monkeypatch)
    monkeypatch.setattr(agent, "create_llm", lambda: _FakeLLM())
    monkeypatch.setattr(agent, "pubmed_loader", _FakePubmedLoader())
    monkeypatch.setattr(agent, "prescription_finder", _RaisingPrescriptionFinder())

    response = run_validation_agent(_request())

    finder_entries = [e for e in response.reasoningTrace if e["action"] == "Prescription Finder"]
    assert finder_entries, "Prescription Finder 스텝이 트레이스에 있어야 한다"
    assert finder_entries[0]["source"] == "fallback"
    assert finder_entries[0]["observation"]["status"] == "FAILED"
