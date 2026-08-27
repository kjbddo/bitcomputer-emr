import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";

import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(__dirname, "../../..");

/**
 * 재스킨이 끝난 영역만 스캔한다. Task 12 에서 ["src"] 로 확대한다.
 * 존재하지 않는 경로는 조용히 건너뛴다.
 */
const SCAN_DIRS = ["src/styles", "src/components/ui", "src/components/theme"];

/** 색상 리터럴이 허용되는 유일한 파일. */
const ALLOWED = new Set(["src/styles/tokens.css"]);

const SCAN_EXTENSIONS = [".css", ".tsx", ".ts"];

const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(/;

/**
 * 선언 값 위치에 온 CSS 색상 키워드.
 *
 * hex 나 rgb() 만 막으면 `color: white` 가 그대로 통과한다. 이관 시작 시점에
 * 코드베이스에 48곳(white 42, red 3, blue 3) 있었고, 남으면 다크 모드에서
 * hex 를 남긴 것과 똑같이 깨진다.
 *
 * .css 에만 적용한다. .tsx 에 걸면 `{ status: "red" }` 같은 평범한 객체 리터럴을
 * 오탐한다. 도입 시점에 .tsx 인라인 스타일의 키워드 색상은 0건이었다.
 *
 * transparent / currentColor / inherit 는 테마를 깨지 않으므로 목록에서 뺀다.
 */
const CSS_COLOR_KEYWORD =
  /:[^;{}]*\b(?:white|black|red|blue|green|yellow|orange|purple|pink|gray|grey|silver|cyan|magenta|lime|navy|teal|olive|maroon|aqua|fuchsia|brown)\b/i;

function walk(dir: string, acc: string[] = []): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return acc;
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "__tests__" || entry === "node_modules") continue;
      walk(full, acc);
    } else if (SCAN_EXTENSIONS.some((ext) => entry.endsWith(ext))) {
      acc.push(full);
    }
  }
  return acc;
}

function offences(): string[] {
  const found: string[] = [];
  for (const dir of SCAN_DIRS) {
    for (const file of walk(join(WEB_ROOT, dir))) {
      const rel = relative(WEB_ROOT, file).split(sep).join("/");
      if (ALLOWED.has(rel)) continue;
      const isCss = rel.endsWith(".css");
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, index) => {
        if (COLOR_LITERAL.test(line) || (isCss && CSS_COLOR_KEYWORD.test(line))) {
          found.push(`${rel}:${index + 1}  ${line.trim()}`);
        }
      });
    }
  }
  return found;
}

describe("색상 리터럴 가드", () => {
  it("tokens.css 밖에서 색상 리터럴을 쓰지 않는다", () => {
    expect(offences()).toEqual([]);
  });
});
