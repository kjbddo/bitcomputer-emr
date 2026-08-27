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
      const lines = readFileSync(file, "utf8").split("\n");
      lines.forEach((line, index) => {
        if (COLOR_LITERAL.test(line)) {
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
