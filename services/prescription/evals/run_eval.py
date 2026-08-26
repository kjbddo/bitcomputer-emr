from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

EVAL_DIR = Path(__file__).resolve().parent
SERVICE_DIR = EVAL_DIR.parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from common import LlmJsonClient, load_default_env_files, read_jsonl, render_prompt, write_jsonl  # noqa: E402
from metrics import aggregate, heuristic_answer_quality, heuristic_hallucination, score_tool_path  # noqa: E402


PROMPT_DIR = EVAL_DIR / "prompts"
TOOL_PATH_PROMPT = PROMPT_DIR / "tool_path_judge.md"
ANSWER_QUALITY_PROMPT = PROMPT_DIR / "answer_quality_judge.md"
HALLUCINATION_PROMPT = PROMPT_DIR / "hallucination_judge.md"


def request_to_mock_response(scenario: Dict[str, Any]) -> Dict[str, Any]:
    request = scenario.get("request") or {}
    top_rx = request.get("top_rx") if isinstance(request.get("top_rx"), list) else []
    items: List[Dict[str, Any]] = []
    usable_rows = [row for row in top_rx if isinstance(row, dict) and (row.get("prescription_name") or row.get("canonical_name") or row.get("prescription_code"))]
    for index in range(3):
        row = usable_rows[index] if index < len(usable_rows) else {}
        name = (
            row.get("prescription_name")
            or row.get("canonical_name")
            or row.get("name")
            or row.get("처방명")
            or "데이터 부족: top_rx 비어 있음"
        )
        code = row.get("prescription_code") or row.get("code") or row.get("처방코드") or "미기재"
        dosage = row.get("dose") or row.get("dosage") or "미기재"
        reason = "입력 top_rx와 유사 환자/그래프 근거를 우선 확인한 mock 평가 응답입니다."
        if not usable_rows:
            reason = "그래프·코호트 데이터가 부족하여 근거 부족을 명시하는 mock 평가 응답입니다."
        items.append({
            "rank": index + 1,
            "name": str(name),
            "prescription_code": str(code),
            "dosage": str(dosage),
            "reason": reason,
            "confidence_score": None,
        })

    disease_codes = [str(code).strip() for code in request.get("disease_codes") or [] if str(code).strip()]
    top_rx_empty = not bool(top_rx)
    trace = []
    trace.append({"tool": "confidence_scores", "called": bool(disease_codes), "status": "mock"})
    trace.append({
        "tool": "top_rx_from_arango",
        "called": bool(request.get("fetch_top_rx_from_arango", True) and top_rx_empty),
        "status": "mock",
    })
    trace.append({
        "tool": "cohort_rx_from_arango",
        "called": bool(request.get("fetch_cohort_rx_from_arango", True) and disease_codes),
        "status": "mock",
    })
    trace.extend([
        {"tool": "prompt_builder", "called": True, "status": "mock"},
        {"tool": "llm_generate", "called": True, "status": "mock"},
        {"tool": "json_parse", "called": True, "status": "mock"},
    ])
    return {
        "prescriptions": items,
        "used_arango_top_rx": False,
        "arango_top_rx_count": 0,
        "used_cohort_rx": False,
        "cohort_rx_count": 0,
        "toolTrace": trace,
    }


def run_agent_direct(scenario: Dict[str, Any]) -> Dict[str, Any]:
    from prescription_api import PrescriptionRecommendRequest, recommend

    old_trace = os.environ.get("PRESCRIPTION_EVAL_TRACE_ENABLED")
    os.environ["PRESCRIPTION_EVAL_TRACE_ENABLED"] = "true"
    try:
        response = recommend(PrescriptionRecommendRequest(**scenario["request"]))
    finally:
        if old_trace is None:
            os.environ.pop("PRESCRIPTION_EVAL_TRACE_ENABLED", None)
        else:
            os.environ["PRESCRIPTION_EVAL_TRACE_ENABLED"] = old_trace
    return response.model_dump(mode="json")


def scenario_with_agent_overrides(
    scenario: Dict[str, Any],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    if not args.agent_model and args.agent_temperature is None:
        return scenario
    overridden = copy.deepcopy(scenario)
    request = overridden.setdefault("request", {})
    if args.agent_model:
        request["model"] = args.agent_model
    if args.agent_temperature is not None:
        request["temperature"] = args.agent_temperature
    return overridden


def run_agent_http(scenario: Dict[str, Any], api_url: str) -> Dict[str, Any]:
    with httpx.Client(timeout=180.0) as client:
        response = client.post(
            api_url.rstrip("/") + "/api/agent/prescription/recommend",
            json=scenario["request"],
            headers={"X-Prescription-Eval-Trace": "true"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text[:1000]
            raise RuntimeError(f"{exc}; body={body}") from exc
        return response.json()


def create_judges(args: argparse.Namespace) -> List[LlmJsonClient]:
    model_by_provider = {
        "openai": args.openai_judge_model,
        "gemini": args.gemini_judge_model,
        "anthropic": args.anthropic_judge_model,
    }
    return [
        LlmJsonClient(
            provider=provider,
            model=model_by_provider[provider],
            timeout=args.judge_timeout,
            temperature=0.0,
        )
        for provider in args.judge_provider
    ]


def call_judge(
    judges: List[LlmJsonClient],
    prompt_path: Path,
    scenario: Dict[str, Any],
    tool_trace: List[Dict[str, Any]],
    final_response: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not judges:
        return None
    prompt = render_prompt(
        prompt_path.read_text(encoding="utf-8"),
        SCENARIO_JSON=scenario,
        TOOL_TRACE_JSON=tool_trace,
        FINAL_RESPONSE_JSON=final_response,
    )
    result = judges[0].complete_json(prompt)
    result["judge"] = judges[0].name
    return result


def infer_expected_tool_path(scenario: Dict[str, Any]) -> Dict[str, Any]:
    expected = scenario.get("expectedToolPath")
    if isinstance(expected, dict) and expected.get("requiredTools"):
        return expected
    request = scenario.get("request") or {}
    required = ["prompt_builder", "llm_generate", "json_parse"]
    forbidden: List[str] = []
    if request.get("disease_codes"):
        required.append("confidence_scores")
        if request.get("fetch_cohort_rx_from_arango", True):
            required.append("cohort_rx_from_arango")
    else:
        forbidden.extend(["confidence_scores", "cohort_rx_from_arango"])
    if request.get("fetch_top_rx_from_arango", True) and not request.get("top_rx"):
        required.append("top_rx_from_arango")
    elif not request.get("fetch_top_rx_from_arango", True):
        forbidden.append("top_rx_from_arango")
    return {
        "requiredTools": list(dict.fromkeys(required)),
        "optionalTools": [],
        "forbiddenTools": forbidden,
        "expectedOrder": list(dict.fromkeys(required)),
        "rationale": "Inferred from request flags.",
    }


def evaluate_case(
    scenario: Dict[str, Any],
    args: argparse.Namespace,
    judges: List[LlmJsonClient],
) -> Dict[str, Any]:
    case_id = scenario.get("caseId")
    scenario = scenario_with_agent_overrides(scenario, args)
    if args.mock_agent:
        response = request_to_mock_response(scenario)
    elif args.api_url:
        response = run_agent_http(scenario, args.api_url)
    else:
        response = run_agent_direct(scenario)

    tool_trace = response.get("toolTrace") or []
    gold_tool_path = infer_expected_tool_path(scenario)
    tool_score = score_tool_path(tool_trace, gold_tool_path)

    if args.skip_judges:
        answer_quality = heuristic_answer_quality(scenario, response)
        hallucination = heuristic_hallucination(scenario, response)
        tool_judgment = None
    else:
        tool_judgment = call_judge(judges, TOOL_PATH_PROMPT, scenario, tool_trace, response)
        if tool_judgment and tool_judgment.get("requiredTools"):
            tool_score = score_tool_path(tool_trace, tool_judgment)
        answer_quality = call_judge(judges, ANSWER_QUALITY_PROMPT, scenario, tool_trace, response)
        hallucination = call_judge(judges, HALLUCINATION_PROMPT, scenario, tool_trace, response)

    return {
        "caseId": case_id,
        "category": scenario.get("category"),
        "controlGroup": scenario.get("controlGroup"),
        "scenario": scenario,
        "agentResponse": response,
        "toolTrace": tool_trace,
        "goldToolPath": gold_tool_path,
        "toolJudgment": tool_judgment,
        "toolScore": tool_score,
        "answerQuality": answer_quality or {},
        "hallucinationJudgment": hallucination or {},
    }


def render_report(summary: Dict[str, Any], result_path: Path) -> str:
    tool = summary.get("toolPathMetrics") or {}
    quality = summary.get("answerQuality") or {}
    hallucination = summary.get("hallucination") or {}
    lines = [
        "# Prescription Agent Evaluation Report",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Raw results: `{result_path.name}`",
        f"- Case count: {summary.get('caseCount')}",
        f"- Successful cases: {summary.get('successfulCases')}",
        f"- Error cases: {summary.get('errorCases')}",
        "",
        "## Tool Path Metrics",
        "",
        f"- Precision: {tool.get('precision')}",
        f"- Recall: {tool.get('recall')}",
        f"- F1: {tool.get('f1')}",
        "",
        "## Answer Quality",
        "",
        f"- Judged cases: {quality.get('judgedCases')}",
        f"- Average overall score: {quality.get('averageOverallScore')}",
        "",
        "## Hallucination",
        "",
        f"- Judged cases: {hallucination.get('judgedCases')}",
        f"- Hallucination rate: {hallucination.get('hallucinationRate')}",
        "",
        "## By Control Group",
        "",
    ]
    for group, values in (summary.get("byControlGroup") or {}).items():
        lines.append(f"- `{group}`: {values}")
    lines.append("")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    load_default_env_files(args.env_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result_path = output_dir / f"prescription_eval_results_{run_id}.jsonl"
    summary_path = output_dir / f"prescription_eval_summary_{run_id}.json"
    report_path = output_dir / f"prescription_eval_report_{run_id}.md"

    scenarios: List[Dict[str, Any]] = []
    for path in args.scenarios:
        scenarios.extend(read_jsonl(Path(path)))
    if args.limit:
        scenarios = scenarios[:args.limit]

    judges = [] if args.skip_judges else create_judges(args)
    results: List[Dict[str, Any]] = []
    for index, scenario in enumerate(scenarios, start=1):
        print(f"[{index}/{len(scenarios)}] running {scenario.get('caseId')}", flush=True)
        try:
            results.append(evaluate_case(scenario, args, judges))
        except Exception as exc:  # noqa: BLE001
            results.append({
                "caseId": scenario.get("caseId"),
                "category": scenario.get("category"),
                "controlGroup": scenario.get("controlGroup"),
                "scenario": scenario,
                "error": str(exc),
            })
        write_jsonl(result_path, results)

    summary = aggregate(results)
    summary["runConfig"] = {
        "scenarios": [str(path) for path in args.scenarios],
        "mockAgent": args.mock_agent,
        "apiUrl": args.api_url,
        "skipJudges": args.skip_judges,
        "judgeProviders": args.judge_provider,
        "agentModelOverride": args.agent_model,
        "agentTemperatureOverride": args.agent_temperature,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_report(summary, result_path), encoding="utf-8")
    print(f"results: {result_path}")
    print(f"summary: {summary_path}")
    print(f"report: {report_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Prescription Agent output/tool path/hallucination.")
    parser.add_argument("--scenarios", nargs="+", required=True)
    parser.add_argument("--output-dir", default=str(EVAL_DIR / "results"))
    parser.add_argument("--api-url", default="")
    parser.add_argument("--mock-agent", action="store_true")
    parser.add_argument("--skip-judges", action="store_true")
    parser.add_argument("--judge-provider", action="append", choices=["openai", "gemini", "anthropic"], default=[])
    parser.add_argument("--openai-judge-model", default="gpt-4o-mini")
    parser.add_argument("--gemini-judge-model", default="gemini-2.0-flash")
    parser.add_argument("--anthropic-judge-model", default="claude-sonnet-4-5")
    parser.add_argument("--judge-timeout", type=float, default=120.0)
    parser.add_argument("--agent-model", default="", help="Override prescription agent request.model for eval runs.")
    parser.add_argument("--agent-temperature", type=float, default=None, help="Override prescription agent request.temperature.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--env-file", action="append", default=[])
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_arg_parser().parse_args()))
