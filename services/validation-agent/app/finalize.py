"""결정론적 최종 판정과 응답 정규화.

`agent.py` 에서 떼어냈다. **이 파일에는 모델 호출이 없다.** `overallStatus`,
`summary`, `reason`, `checks`, `suspectedIssues` 는 전부 여기 있는 순수 함수의
출력이다 — 옛 `_llm_finalize` 는 어떤 경로로도 호출되지 않았고(F-M2) 함께
삭제했으므로, 이제 그 사실이 코드 구조로도 드러난다.

호출부(`agent.py`)는 이 판정이 규칙에서 나왔다는 것을 트레이스의
`Rule-based Finalize` 스텝으로 명시한다 — 그래야 화면이 이 문장들을 모델
추론으로 읽지 않는다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .state import ValidationState


def rule_based_finalize(state: ValidationState) -> Dict[str, Any]:
    disease_check = state.get("disease_check") or {}
    prescription_check = state.get("prescription_check") or {}
    disease_status = disease_check.get("status")
    prescription_status = prescription_check.get("status")

    suspected_issues: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    if disease_status in {"MISMATCH", "PARTIAL_MATCH"}:
        severity = "HIGH" if disease_status == "MISMATCH" else "MEDIUM"
        suspected_issues.append({
            "severity": severity,
            "category": "XRAY_CONFLICT",
            "description": "저장 상병과 X-ray 추론 결과의 불일치 가능성이 있습니다.",
            "reason": "; ".join(map(str, disease_check.get("evidence") or [])),
        })
        checks.append({
            "type": "DISEASE_XRAY_CONSISTENCY",
            "status": "CRITICAL" if severity == "HIGH" else "WARNING",
            "message": "X-ray 추론 상병 일부가 저장 상병에 반영되지 않았을 수 있습니다.",
            "evidence": disease_check.get("evidence") or [],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": [],
            "recommendedAction": "의료진이 저장 상병과 영상판독 결과를 함께 재확인하세요.",
        })

    if prescription_status == "INSUFFICIENT_DATA":
        checks.append({
            "type": "DISEASE_PRESCRIPTION_CONSISTENCY",
            "status": "INSUFFICIENT_DATA",
            "message": "처방 검증에 필요한 데이터가 부족합니다.",
            "evidence": prescription_check.get("evidence") or [],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("saved_prescriptions", []),
            "recommendedAction": "상병, 증상, 처방 입력이 모두 저장되었는지 확인하세요.",
        })
    elif prescription_status:
        checks.append({
            "type": "DISEASE_PRESCRIPTION_CONSISTENCY",
            "status": "PASS",
            "message": "저장 상병/증상과 처방 검증에 필요한 기본 데이터가 확인되었습니다.",
            "evidence": prescription_check.get("evidence") or [],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("saved_prescriptions", []),
            "recommendedAction": "의료진 최종 검토를 유지하세요.",
        })

    if not checks:
        checks.append({
            "type": "DATA_QUALITY",
            "status": "PASS",
            "message": "검증 가능한 범위에서 큰 불일치가 발견되지 않았습니다.",
            "evidence": ["기본 검증 규칙을 통과했습니다."],
            "relatedDiseases": state.get("saved_diseases", []),
            "relatedPrescriptions": state.get("saved_prescriptions", []),
            "recommendedAction": "일반적인 의료진 검토 절차를 따르세요.",
        })

    if any(issue.get("severity") == "HIGH" for issue in suspected_issues):
        overall = "CRITICAL"
    elif suspected_issues:
        overall = "WARNING"
    elif any(check.get("status") == "INSUFFICIENT_DATA" for check in checks):
        overall = "NEEDS_REVIEW"
    else:
        overall = "PASS"

    return normalize_final_result({
        "overallStatus": overall,
        "summary": summary_for(overall),
        "reason": reason_from_checks(checks, suspected_issues),
        "checks": checks,
        "suspectedIssues": suspected_issues,
        "suggestedReviewItems": review_items(overall),
        "candidatePrescriptions": state.get("candidate_prescriptions", []),
        "shouldNotifyDoctor": overall in {"WARNING", "CRITICAL", "NEEDS_REVIEW"},
        "shouldBlockAutoPrescription": overall == "CRITICAL",
    })


def normalize_final_result(result: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"PASS", "WARNING", "CRITICAL", "NEEDS_REVIEW"}
    overall = str(result.get("overallStatus") or "NEEDS_REVIEW").upper()
    if overall not in allowed:
        overall = "NEEDS_REVIEW"
    return {
        "jobId": result.get("jobId"),
        "historyId": result.get("historyId"),
        "overallStatus": overall,
        "summary": str(result.get("summary") or summary_for(overall)),
        "reason": str(result.get("reason") or reason_from_checks(
            result.get("checks") if isinstance(result.get("checks"), list) else [],
            result.get("suspectedIssues") if isinstance(result.get("suspectedIssues"), list) else [],
        )),
        "recommendedPrescriptions": (
            result.get("recommendedPrescriptions")
            if isinstance(result.get("recommendedPrescriptions"), list)
            else result.get("candidatePrescriptions")
            if isinstance(result.get("candidatePrescriptions"), list)
            else []
        ),
        "validation": result.get("validation") if isinstance(result.get("validation"), dict) else {},
        "reasoningTrace": result.get("reasoningTrace") if isinstance(result.get("reasoningTrace"), list) else [],
        "checks": result.get("checks") if isinstance(result.get("checks"), list) else [],
        "suspectedIssues": result.get("suspectedIssues") if isinstance(result.get("suspectedIssues"), list) else [],
        "suggestedReviewItems": (
            result.get("suggestedReviewItems")
            if isinstance(result.get("suggestedReviewItems"), list)
            else review_items(overall)
        ),
        "candidatePrescriptions": (
            result.get("candidatePrescriptions")
            if isinstance(result.get("candidatePrescriptions"), list)
            else []
        ),
        "shouldNotifyDoctor": bool(result.get("shouldNotifyDoctor", overall != "PASS")),
        "shouldBlockAutoPrescription": bool(result.get("shouldBlockAutoPrescription", overall == "CRITICAL")),
        # 설정이 아니라 실행 경로에서 나온 값을 그대로 통과시킨다(spec §6.2, GC-3).
        "llmStatus": str(result.get("llmStatus") or "fallback"),
    }


def normalize_prescription_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        normalized.append({
            "id": int(row.get("id") or 0),
            "rank": int(row.get("rank") or index),
            "prescription_code": row.get("prescription_code") or row.get("code") or "",
            "prescription_name": row.get("prescription_name") or row.get("name") or "",
            "reason": row.get("reason") or "",
            "confidence_score": float(row.get("confidence_score") or row.get("confidenceScore") or 0),
            "dose": int(row.get("dose") or 0),
            "time": int(row.get("time") or 0),
            "days": int(row.get("days") or 0),
        })
    return normalized


def summary_for(overall: str) -> str:
    return {
        "PASS": "검증 가능한 범위에서 큰 불일치가 발견되지 않았습니다.",
        "WARNING": "일부 데이터에서 의료진 확인이 필요한 불일치 가능성이 있습니다.",
        "CRITICAL": "상병, 처방 또는 X-ray 추론 결과 사이에 강한 불일치 가능성이 있습니다.",
        "NEEDS_REVIEW": "자동 검증에 필요한 데이터가 부족하여 의료진 검토가 필요합니다.",
    }.get(overall, "의료진 검토가 필요합니다.")


def reason_from_checks(checks: List[Dict[str, Any]], suspected_issues: List[Dict[str, Any]]) -> str:
    issue_reasons = [
        str(issue.get("reason") or issue.get("description") or "").strip()
        for issue in suspected_issues
        if str(issue.get("reason") or issue.get("description") or "").strip()
    ]
    if issue_reasons:
        return " / ".join(issue_reasons[:2])

    check_reasons = [
        str(check.get("message") or check.get("recommendedAction") or "").strip()
        for check in checks
        if str(check.get("message") or check.get("recommendedAction") or "").strip()
    ]
    if check_reasons:
        return " / ".join(check_reasons[:2])

    return "검증 결과를 판단할 세부 근거가 충분하지 않아 기본 요약을 사용했습니다."


def review_items(overall: str) -> List[str]:
    if overall == "PASS":
        return []
    return [
        "저장 상병 코드와 상병명을 확인하세요.",
        "저장 처방이 현재 상병 및 증상과 관련 있는지 확인하세요.",
        "X-ray 추론 결과와 실제 영상 소견을 함께 확인하세요.",
    ]
