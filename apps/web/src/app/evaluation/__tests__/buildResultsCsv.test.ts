import { describe, expect, it } from "vitest";
import { buildResultsCsv } from "../buildResultsCsv";

// 헤더와 행이 두 개의 손으로 관리하는 목록이라, 한쪽에만 컬럼을 넣거나 빼면
// 그 뒤 컬럼이 전부 한 칸씩 밀린 채 나간다. 파일은 여전히 정상으로 보인다.
// Task 9(실 Bedrock 측정)가 이 CSV 를 소비하므로 밀림이 숫자를 조용히 오염시킨다.

function parseRow(line: string): string[] {
  // escapeCsvCell 이 쓰는 최소 규칙만 되돌린다: 따옴표로 감싸고 "" 로 이스케이프.
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      cells.push(cell);
      cell = "";
    } else {
      cell += ch;
    }
  }
  cells.push(cell);
  return cells;
}

const ROW = {
  rowNumber: 1,
  diseaseCode: "J00",
  prescriptionCode: "P1",
  prescriptionName: "약",
  status: "success" as const,
  medicalCertificate: "소견",
  llmStatus: "fallback",
};

describe("buildResultsCsv", () => {
  it("헤더 셀 수와 각 행의 셀 수가 같다", () => {
    const lines = buildResultsCsv([ROW]).split("\n");
    const header = parseRow(lines[0]);

    expect(header.length).toBeGreaterThan(1);
    for (const line of lines.slice(1).filter((l) => l.length > 0)) {
      expect(parseRow(line).length).toBe(header.length);
    }
  });

  it("llmStatus 가 자기 컬럼 위치에 실리고 뒤 컬럼을 밀지 않는다", () => {
    const lines = buildResultsCsv([ROW]).split("\n");
    const header = parseRow(lines[0]);
    const row = parseRow(lines[1]);

    const index = header.indexOf("llmStatus");
    expect(index).toBeGreaterThan(-1);
    expect(row[index]).toBe("fallback");
    // 바로 다음 컬럼이 여전히 score 여야 한다. 한 칸 밀리면 여기서 걸린다.
    expect(header[index + 1]).toBe("score");
  });

  // 이 값을 리터럴로 하드코딩하면 Task 9 의 측정 산출물에서 폴백 행과 모델 행이
  // 구분되지 않는다 — 이 플랜이 막으려는 결함 그 자체다.
  it("행마다 자기 llmStatus 를 싣는다", () => {
    const lines = buildResultsCsv([
      { ...ROW, rowNumber: 1, llmStatus: "real" },
      { ...ROW, rowNumber: 2, llmStatus: "fallback" },
    ]).split("\n");
    const index = parseRow(lines[0]).indexOf("llmStatus");

    expect(parseRow(lines[1])[index]).toBe("real");
    expect(parseRow(lines[2])[index]).toBe("fallback");
  });
});
