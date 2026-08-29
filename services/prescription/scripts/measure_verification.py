"""검증층이 실제로 무엇을 잡는지 센다(spec §11).

앞의 두 항목(flagged/skipped 비율)은 LLM 키 없이 stub 모드로도 돌지만,
그 숫자는 **스텁의 출력**을 설명할 뿐 모델의 조작 경향을 말해주지 않는다.
결과를 spec §11 에 적을 때 그 구분을 지워서는 안 된다.

키를 출력하지 않는다(GC-7).
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from typing import Any, Dict, List, Tuple

import httpx

DEFAULT_BASE = "http://localhost:8001"
RECOMMEND_PATH = "/api/agent/prescription/recommend"


def load_scenarios(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenarios")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    scenarios = load_scenarios(args.scenarios)
    status_counts: collections.Counter = collections.Counter()
    check_counts: collections.Counter = collections.Counter()
    http_failures: List[str] = []
    flagged_details: List[Tuple[str, Any, Any, Any]] = []

    with httpx.Client(timeout=args.timeout) as client:
        for scenario in scenarios:
            case_id = scenario.get("caseId", "?")
            try:
                response = client.post(
                    f"{args.base_url}{RECOMMEND_PATH}", json=scenario["request"]
                )
            except Exception as exc:  # noqa: BLE001
                http_failures.append(f"{case_id}: {type(exc).__name__}")
                status_counts["transport_error"] += 1
                continue

            if response.status_code != 200:
                http_failures.append(f"{case_id}: HTTP {response.status_code}")
                status_counts[f"http_{response.status_code}"] += 1
                continue

            verification = response.json().get("verification")
            if verification is None:
                status_counts["field_missing"] += 1
                continue

            status_counts[verification.get("status", "no_status")] += 1
            for check in verification.get("checks") or []:
                check_counts[(check.get("id"), check.get("outcome"))] += 1
                # flagged 는 이 계측이 찾는 유일한 사건이다. 집계 숫자만 남기면
                # "왜 걸렸는지"를 되물을 수 없다 — 4차 실측에서 실제로 한 건이
                # 발화했는데 evidence 를 버려서 원인을 끝내 못 밝혔다.
                if check.get("outcome") == "flagged":
                    flagged_details.append(
                        (case_id, check.get("id"), check.get("target"),
                         check.get("evidence"))
                    )

    total = len(scenarios)
    print(f"시나리오 {total}건\n")

    print("verification.status 분포:")
    for key, count in status_counts.most_common():
        print(f"  {key:16s} {count:3d}  ({count / total:.0%})")

    print("\n검사별 결과:")
    by_check: Dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for (check_id, outcome), count in check_counts.items():
        by_check[check_id][outcome] += count
    for check_id in sorted(by_check):
        outcomes = by_check[check_id]
        n = sum(outcomes.values())
        parts = " ".join(f"{k}={v}" for k, v in sorted(outcomes.items()))
        print(f"  {check_id:22s} {parts:34s} (총 {n})")

    if flagged_details:
        print(f"\nflagged {len(flagged_details)}건 (근거 전문):")
        for case_id, check_id, target, evidence in flagged_details:
            print(f"  [{case_id}] {check_id} @ {target}")
            print(f"      {evidence}")

    if http_failures:
        print(f"\n응답을 못 받은 케이스 {len(http_failures)}건:")
        for line in http_failures[:10]:
            print(f"  {line}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
