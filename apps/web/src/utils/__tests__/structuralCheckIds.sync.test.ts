import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { STRUCTURAL_CHECK_IDS } from "../verificationNotice";

// IMP-2 — verificationNotice.ts 의 itemVerificationOutcome 이 구조 검사
// (STRUCTURAL_CHECK_IDS) 를 항목 배지의 grounding 판정에서 제외하려면, 웹이
// 그 id 집합을 알아야 한다. Python 쪽 STRUCTURAL_CHECK_IDS
// (services/prescription/verification_contract.py,
// services/validation-agent/app/verification_contract.py — 이 둘은 이미
// tests/test_verification.py::test_contract_copy_matches_prescription 으로
// 본문 동일성이 고정돼 있다) 와 값이 갈라지면, 웹은 구조 검사가 아닌 것을
// 구조 검사로(또는 그 반대로) 취급하게 된다. 이 테스트는 두 파이썬 소스를
// 직접 파싱해서 이 TS 상수와 비교한다 — 세 곳 중 어느 하나만 고치면 여기서
// 즉시 red 가 된다.
const WEB_ROOT = resolve(__dirname, "../../..");
const REPO_ROOT = resolve(WEB_ROOT, "../..");

const PYTHON_CONTRACT_FILES = [
  resolve(REPO_ROOT, "services/prescription/verification_contract.py"),
  resolve(REPO_ROOT, "services/validation-agent/app/verification_contract.py"),
];

function parsePythonStructuralCheckIds(filePath: string): string[] {
  const source = readFileSync(filePath, "utf-8");
  const match = source.match(/STRUCTURAL_CHECK_IDS\s*=\s*frozenset\(\s*\{([^}]*)\}\s*\)/);
  if (!match) {
    throw new Error(`STRUCTURAL_CHECK_IDS frozenset literal not found in ${filePath}`);
  }
  const body = match[1];
  const ids = [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  if (ids.length === 0) {
    throw new Error(`STRUCTURAL_CHECK_IDS parsed to an empty set in ${filePath}`);
  }
  return ids;
}

describe("STRUCTURAL_CHECK_IDS — Python/TS 동기화", () => {
  for (const filePath of PYTHON_CONTRACT_FILES) {
    it(`${filePath} 의 STRUCTURAL_CHECK_IDS 와 값이 일치한다`, () => {
      const pythonIds = parsePythonStructuralCheckIds(filePath).sort();
      const tsIds = [...STRUCTURAL_CHECK_IDS].sort();
      expect(tsIds).toEqual(pythonIds);
    });
  }
});
