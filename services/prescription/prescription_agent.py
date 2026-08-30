# -*- coding: utf-8 -*-
"""
의료 그래프 기반 처방 추천 에이전트용 사용자 메시지 프롬프트.

Spring Boot 등에서 동일 본문을 쓸 때는 {patient_id}, {symptoms} 등 템플릿 변수로 치환하면 됩니다.
이 모듈에서는 예시 JSON의 중괄호와 충돌하지 않도록 <<<PLACEHOLDER>>> 토큰만 치환합니다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# 그대로 치환할 토큰 (본문·형식 예시 안의 중괄호와 충돌하지 않게 분리)
_PH_PATIENT_ID = "<<<PATIENT_ID>>>"
_PH_SYMPTOMS = "<<<SYMPTOMS>>>"
_PH_HISTORY = "<<<HISTORY>>>"
_PH_TOP_RX = "<<<TOP_RX>>>"
_PH_SIMILAR = "<<<SIMILAR_OUTCOMES>>>"
_PH_OPTIONAL_MENTION = "<<<OPTIONAL_MENTION_BLOCK>>>"
_PH_OPTIONAL_CLINICIAN = "<<<OPTIONAL_CLINICIAN_BLOCK>>>"
_PH_RANKED_SLATE = "<<<RANKED_SLATE>>>"

PRESCRIPTION_AGENT_PROMPT = """## Role
당신은 ArangoDB 기반 의료 그래프 조회 결과를 의사에게 **설명하는** AI 의료 어시스턴트입니다.
처방을 고르거나 순위를 매기는 것은 당신의 일이 아닙니다 — 그것은 아래 "확정된 추천 순위"가 이미 끝냈습니다.

## Context
1. 데이터 소스: ArangoDB 그래프 — 문서: visits, diagnoses, prescription_masters, order_lines, special_notes, note_mentions
   엣지: visit_has_diagnosis, visit_has_order, order_refers_prescription, visit_has_note, order_associated_diagnosis,
   note_has_mention(특이사항→mention), diagnosis_has_mention(상병→mention), prescription_has_mention(처방마스터→mention).
   note_mentions 조각(mention) 필드: note_id, visit_id, mention_type, 원문 text, normalized_text, normalized_text_light,
   tokens, is_abbreviation, match_candidates — 적재 후 Arango에서는 논리 mention_id가 문서 _key에만 있으므로(본문 속성 mention_id 없음)
   백엔드·AQL 결과에 _key가 있으면 그것이 mention 식별자입니다.
   CSV `17_rel_diagnosis_has_mention.csv`, `18_rel_prescription_has_mention.csv` 가 이 두 엣지를 적재합니다.
2. 타겟: 현재 환자의 증상, 과거 진단 이력(History), 유사 환자 처방 사례, (선택) 상병·처방과 특이사항 mention 간 직접 연결 요약.
3. 기술 스택: Spring Boot (Back-End), ArangoDB, LangChain.

## Constraints
1. 출력은 반드시 순수 JSON 형태여야 하며, 다른 서술형 문장은 포함하지 마십시오.
2. **순위·처방명·처방코드는 이미 확정되어 있습니다.** 아래 "확정된 추천 순위" 표의 rank·name·prescription_code를 **한 글자도 바꾸지 말고 그대로** 옮겨 적으십시오. 순서를 바꾸거나, 표에 없는 처방을 넣거나, 표의 처방을 빼지 마십시오. (서비스가 이 세 필드를 조회 결과로 덮어쓰므로 바꿔 봐야 반영되지 않습니다.)
3. **당신이 실제로 쓰는 것은 각 항목의 `reason` 한 단락뿐입니다.** 이 환자 맥락에서 이 처방이 왜 타당한지 / 무엇을 주의해야 하는지를 한국어로 짧게 쓰십시오.
4. **데이터 앵커 + 임상 해석**: `reason`은 먼저 아래 Patient Context·top_rx·mention·similar_outcomes에 **실제로 등장한** 처방명·코드·증상·토큰을 인용한 뒤, 그 안에서만 **일반적인 의학·약리 지식**(약 계열, 상호작용 개념, 감시 항목 등)을 짧게 보강할 수 있습니다. 입력에 없는 진단·처방 **사실**을 새로 만들지는 마십시오.
5. **dosage**: 입력에 용량이 없으면 `"미기재"` 또는 `"데이터에 용량 없음"`만 사용하고, 임의 mg/cc를 지어내지 마십시오.
6. 표의 어떤 순위가 `"데이터 부족: 조회된 처방 후보 없음"` 이면, 그 순위를 채울 약품을 **제안하지 마십시오**. `name`·`prescription_code`를 표 그대로 두고, `reason`에는 "이 상병에 대해 우리 데이터가 뒷받침하는 후보가 이 순위까지 없다"는 사실만 적으십시오. 그것이 유용한 신호입니다.

아래의 환자 상태와 ArangoDB 그래프 조회 결과를 읽고, 확정된 3개 순위 각각에 대한 설명을 쓰십시오.

### Patient Context
- Patient ID: <<<PATIENT_ID>>>
- Current Symptoms: <<<SYMPTOMS>>>
- Medical History: <<<HISTORY>>>

### ArangoDB Graph Insights (AQL Result)
- Top Frequency Prescriptions for Disease: <<<TOP_RX>>>
- Similar Patient Outcomes: <<<SIMILAR_OUTCOMES>>>

### 확정된 추천 순위 (조회 결과가 정했습니다 — 바꾸지 마십시오)
<<<RANKED_SLATE>>>

<<<OPTIONAL_MENTION_BLOCK>>><<<OPTIONAL_CLINICIAN_BLOCK>>>
### Required JSON Format (Strict)
{
  "prescriptions": [
    {
      "rank": 1,
      "name": "위 표 1순위의 name 을 그대로",
      "prescription_code": "위 표 1순위의 prescription_code 를 그대로",
      "dosage": "미기재 또는 입력에 있는 용량만",
      "reason": "데이터 인용 후, 필요 시 짧은 임상·약리 보강(한국어)"
    },
    { "rank": 2, "name": "...", "prescription_code": "...", "dosage": "...", "reason": "..." },
    { "rank": 3, "name": "...", "prescription_code": "...", "dosage": "...", "reason": "..." }
  ]
}

설명 결과:
"""


def _as_prompt_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value) if value is not None else ""


def _render_ranked_slate(ranked_slate: Any) -> str:
    """조회가 확정한 순위를 프롬프트에 사람이 읽는 표로 넣는다.

    `_sparse_top_rx_appendix`(구 `:118-135`)가 여기 있었다. 그 분기는 후보가
    3건 미만이면 rank 2·3 에 "임상적으로 타당한 병용·대안 처방(실제 제품명·
    성분명)"을 채우라고 모델에게 **명시적으로 허용**했다. 순위·처방명·코드가
    조회로 확정된 지금 그 지시는 모순이다 — 모델이 채운 이름은 서비스가 어차피
    조회 결과로 덮어쓰므로 반영되지 않고, `reason` 에만 존재하지 않는 약에 대한
    설명이 남는다. 그래서 제거했다.

    부수 효과로 §1.1 의 조건부 관측("모델은 지어내지 않는다 — 단 이 분기가
    걸리지 않았을 뿐")이 무조건이 된다. 이는 설계 §3.2(step 2)가 예정한
    제거이기도 하지만, step 1 이 이 분기를 논리적으로 성립 불가능하게 만들어
    먼저 강제했다. §3.2 의 나머지 절반(3건을 채우지 않고 거절을 1급 답으로
    허용 = 응답 항목 수를 줄이는 것)은 여기서 하지 않는다 — 응답 계약을
    바꾸는 일이라 step 2 의 몫이다.
    """
    rows = ranked_slate if isinstance(ranked_slate, (list, tuple)) else []
    if not rows:
        return (
            "(조회된 처방 후보가 0건입니다. 순위를 채울 약품을 제안하지 말고, "
            "세 항목 모두 name 을 `데이터 부족: 조회된 처방 후보 없음`, "
            "prescription_code 를 `미기재`로 두십시오.)"
        )
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rank = row.get("rank")
        name = row.get("name", "")
        code = row.get("prescription_code", "")
        score = row.get("confidence_score")
        if isinstance(score, (int, float)):
            basis = f"confidence {float(score):.4f} (유사 환자 코호트 co-occurrence)"
        else:
            basis = "confidence 없음 — 이 순위는 조회가 준 후보 순서일 뿐 빈도 근거가 없습니다"
        lines.append(f"{rank}. name={name!r}  prescription_code={code!r}  — {basis}")
    return "\n".join(lines)


def _coerce_mention_links_for_prompt(mention_links: Any) -> Any:
    """
    Arango note_mentions / 엣지 조회 JSON을 프롬프트에 넣기 좋게 통일합니다.

    적재 시 mention_id는 _key로만 존재하는 경우가 많아, _key만 있으면 mention_id를 채웁니다.
    """
    if mention_links is None:
        return None

    def _one(row: Any) -> Any:
        if not isinstance(row, dict):
            return row
        out = dict(row)
        mid = out.get("mention_id")
        if mid is None or (isinstance(mid, str) and not mid.strip()):
            k = out.get("_key")
            if isinstance(k, str) and k.strip():
                out["mention_id"] = k.strip()
        return out

    if isinstance(mention_links, list):
        return [_one(x) for x in mention_links]
    return _one(mention_links)


def _optional_mention_section(mention_links: Any) -> str:
    """diagnosis_has_mention / prescription_has_mention·note_mentions 조회 요약이 있을 때만 블록 생성."""
    if mention_links is None:
        return ""
    if isinstance(mention_links, (list, dict)) and len(mention_links) == 0:
        return ""
    coerced = _coerce_mention_links_for_prompt(mention_links)
    body = _as_prompt_text(coerced).strip()
    if not body:
        return ""
    return (
        "### Mention (note_mentions + edges 16–18, optional)\n"
        "각 행의 text·normalized_text·tokens·match_candidates·mention_type·is_abbreviation을 근거로 삼고, "
        "mention_id가 비어 있으면 _key를 동일 식별자로 간주합니다.\n"
        f"{body}\n\n"
    )


def build_prescription_agent_prompt(
    patient_id: Any,
    symptoms: Any,
    history: Any,
    top_rx: Any,
    similar_outcomes: Any,
    ranked_slate: Any,
    clinician_question: str | None = None,
    mention_links: Any | None = None,
) -> str:
    """
    환자·그래프 인사이트를 넣은 단일 사용자 메시지 본문을 만듭니다.

    LangChain / Spring: 이 문자열 전체를 **user** 메시지로 보내는 것이 가장 단순합니다.
    system 메시지는 짧게 두고(역할·JSON만 출력 등), 긴 지시·데이터는 여기에만 두면 됩니다.

    ranked_slate: `ranking.build_ranked_slate` 가 확정한 순위
        (`RankedCandidate.to_prompt_row()` dict 목록). **기본값을 두지 않는다** —
        기본값이 있으면 호출자가 인자를 빠뜨렸을 때 순위가 조용히 모델에게
        되돌아간다. 이 파라미터를 빠뜨리는 것은 TypeError 여야 한다(spec §3.1).
    clinician_question: 의사/화면에서 온 자연어 질문이 있으면 그래프 요약 뒤에 붙습니다. 없으면 생략.
    mention_links: diagnosis_has_mention·prescription_has_mention·note_mentions 기반 AQL/REST 결과(선택).
        note_mentions 본문 필드(note_id, visit_id, mention_type, text, normalized_text, …)와 엣지 메타를 그대로 넣으면 됩니다.
    """
    cq = (clinician_question or "").strip()
    optional_block = (
        f"### Clinician question\n{cq}\n\n" if cq else ""
    )
    base = (
        PRESCRIPTION_AGENT_PROMPT.replace(_PH_PATIENT_ID, _as_prompt_text(patient_id))
        .replace(_PH_SYMPTOMS, _as_prompt_text(symptoms))
        .replace(_PH_HISTORY, _as_prompt_text(history))
        .replace(_PH_TOP_RX, _as_prompt_text(top_rx))
        .replace(_PH_SIMILAR, _as_prompt_text(similar_outcomes))
        .replace(_PH_RANKED_SLATE, _render_ranked_slate(ranked_slate))
        .replace(_PH_OPTIONAL_MENTION, _optional_mention_section(mention_links))
        .replace(_PH_OPTIONAL_CLINICIAN, optional_block)
    )
    return base


def load_prescription_context_file(path: Path) -> dict[str, Any]:
    """
    JSON 파일에서 컨텍스트를 읽습니다.

    필수 키: patient_id, symptoms, history, top_rx, similar_outcomes
    선택 키: mention_links (note_mentions 문서 또는 16–18번 엣지 조인 결과 배열; _key만 있어도 됨)
    run_prescription_agent.py 의 ``--fetch-top-rx-from-arango`` 로 Arango에서 top_rx 를 채우면 이 필드는 실행 시 덮어써질 수 있음.
    (값은 문자열 또는 JSON 배열/객체 가능)
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ("patient_id", "symptoms", "history", "top_rx", "similar_outcomes")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"prescription context JSON에 필수 키가 없습니다: {missing}")
    out: dict[str, Any] = {k: data[k] for k in required}
    if "mention_links" in data:
        out["mention_links"] = data["mention_links"]
    return out


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json_object_from_llm_text(raw: str) -> dict[str, Any]:
    """
    LLM 응답에서 최상위 JSON 객체를 파싱합니다.
    앞뒤 설명문·마크다운 코드 펜스가 있어도 첫 객체를 찾습니다.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("빈 응답입니다.")

    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    dec = json.JSONDecoder()
    start = text.find("{")
    if start < 0:
        raise ValueError("JSON 객체 시작 `{` 를 찾을 수 없습니다.")
    obj, _ = dec.raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("최상위 값은 JSON 객체여야 합니다.")
    return obj


def validate_prescriptions_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Required JSON Format 스키마를 검증하고 prescriptions 배열을 반환합니다."""
    rx = data.get("prescriptions")
    if not isinstance(rx, list) or len(rx) != 3:
        raise ValueError('키 "prescriptions" 는 길이 3인 배열이어야 합니다.')

    required_fields = ("rank", "name", "prescription_code", "dosage", "reason")
    parsed: list[tuple[int, dict[str, Any]]] = []
    for i, item in enumerate(rx):
        if not isinstance(item, dict):
            raise ValueError(f"prescriptions[{i}] 는 객체여야 합니다.")
        missing = [k for k in required_fields if k not in item]
        if missing:
            raise ValueError(f"prescriptions[{i}] 에 필수 키가 없습니다: {missing}")
        try:
            r_int = int(item["rank"])  # type: ignore[arg-type]
        except (TypeError, ValueError) as e:
            raise ValueError(f"prescriptions[{i}].rank 은 정수여야 합니다: {item['rank']!r}") from e
        parsed.append((r_int, dict(item)))

    parsed.sort(key=lambda t: t[0])
    ranks_sorted = [t[0] for t in parsed]
    if ranks_sorted != [1, 2, 3]:
        raise ValueError(
            "prescriptions 의 rank 는 1, 2, 3 이 각각 한 번씩 있어야 합니다 "
            f"(정렬 후: {ranks_sorted!r}). 모델이 순서를 바꿨거나 중복 rank 를 냈을 수 있습니다."
        )

    out: list[dict[str, Any]] = []
    for i, (_r, item) in enumerate(parsed):
        item["rank"] = i + 1
        out.append(item)
    return out


def parse_prescriptions_llm_response(raw: str) -> dict[str, Any]:
    """모델 출력을 파싱·검증한 뒤 prescriptions 스키마를 만족하는 dict를 반환합니다."""
    data = extract_json_object_from_llm_text(raw)
    validate_prescriptions_payload(data)
    return data
