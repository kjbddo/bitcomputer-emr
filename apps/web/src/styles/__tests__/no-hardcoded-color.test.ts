import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";

import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(__dirname, "../../..");

/**
 * 재스킨이 끝난 영역만 스캔한다. Task 12 에서 ["src"] 로 확대한다.
 * 존재하지 않는 경로는 조용히 건너뛴다.
 */
const SCAN_DIRS = [
  "src/styles",
  "src/components/ui",
  "src/components/theme",
  "src/app/(dashboard)",
  "src/app/(auth)/admin",
];

/**
 * 색상 리터럴이 허용되는 파일.
 *
 * `admin/users/page.module.css`는 SCAN_DIRS 가 `src/app/(auth)/admin` 전체로
 * 넓어지며 함께 딸려 들어왔지만, Task 8 의 대상(`layout.tsx`/`layout.module.css`)이
 * 아니다 — 테이블·배지 전면 재스킨이 필요한 별도 분량이라 여기서 손대지 않는다.
 * Header.module.css/Sidebar.module.css 가 Task 12 까지 스캔 밖에 남는 것과 같은
 * 종류의 임시 예외이며, 후속 재스킨 태스크가 이 항목을 지우고 실제로 마이그레이션해야 한다.
 */
const ALLOWED = new Set([
  "src/styles/tokens.css",
  "src/app/(auth)/admin/users/page.module.css",
]);

/**
 * 영구 예외. 나머지 ALLOWED 항목은 임시이며, 아래 "불필요해진 ALLOWED 예외" 테스트가
 * 해당 파일이 정리되는 순간 실패해 항목 제거를 강제한다.
 */
const PERMANENT_ALLOWED = new Set(["src/styles/tokens.css"]);

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

/** 한 파일의 위반 줄을 `경로:줄  내용` 형태로 돌려준다. ALLOWED 를 보지 않는다. */
function fileOffences(absolutePath: string, rel: string): string[] {
  const isCss = rel.endsWith(".css");
  const found: string[] = [];
  readFileSync(absolutePath, "utf8")
    .split("\n")
    .forEach((line, index) => {
      if (COLOR_LITERAL.test(line) || (isCss && CSS_COLOR_KEYWORD.test(line))) {
        found.push(`${rel}:${index + 1}  ${line.trim()}`);
      }
    });
  return found;
}

function offences(): string[] {
  const found: string[] = [];
  for (const dir of SCAN_DIRS) {
    for (const file of walk(join(WEB_ROOT, dir))) {
      const rel = relative(WEB_ROOT, file).split(sep).join("/");
      if (ALLOWED.has(rel)) continue;
      found.push(...fileOffences(file, rel));
    }
  }
  return found;
}

describe("색상 리터럴 가드", () => {
  it("tokens.css 밖에서 색상 리터럴을 쓰지 않는다", () => {
    expect(offences()).toEqual([]);
  });

  /**
   * 임시 예외가 스스로 사라지게 만드는 장치.
   *
   * ALLOWED 항목은 "지금은 리터럴이 있고 나중 태스크가 재스킨한다"는 뜻이다.
   * 그 파일이 실제로 정리되고 나면 예외는 남아 있을 이유가 없는데, 주석만으로는
   * 아무도 지우지 않는다 — 가드가 썩는 전형적인 경로다.
   *
   * 그래서 예외 대상이 더 이상 리터럴을 갖고 있지 않으면 실패시킨다. 재스킨을 끝낸
   * 사람이 ALLOWED 에서 항목을 지우도록 강제된다. 파일이 사라진 경우도 마찬가지다.
   */
  it("불필요해진 ALLOWED 예외를 남겨두지 않는다", () => {
    const stale = [...ALLOWED]
      .filter((rel) => !PERMANENT_ALLOWED.has(rel))
      .filter((rel) => {
        const absolutePath = join(WEB_ROOT, ...rel.split("/"));
        try {
          return fileOffences(absolutePath, rel).length === 0;
        } catch {
          return true; // 파일이 없어졌다면 예외도 필요 없다.
        }
      });
    expect(stale).toEqual([]);
  });
});
