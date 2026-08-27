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
  "src/components/common",
  "src/app/(dashboard)",
  "src/app/(auth)",
];

/**
 * 색상 리터럴이 허용되는 파일.
 *
 * `admin/users/page.module.css`는 SCAN_DIRS 가 관리자 경로까지 넓어지며 함께
 * 딸려 들어왔지만 Task 8 의 대상이 아니었다 — 테이블·배지 전면 재스킨이 필요한
 * 별도 분량이라 Task 12 가 처리한다. 임시 예외이며, 아래 "불필요해진 ALLOWED 예외"
 * 테스트가 그 파일이 정리되는 순간 실패해 이 항목의 제거를 강제한다.
 */
const ALLOWED = new Set([
  "src/styles/tokens.css",
  "src/app/(auth)/admin/users/page.module.css",
]);

/**
 * SCAN_DIRS 가 아직 덮지 않는 디렉터리(`src/components/*`)에 살지만 개별적으로
 * 재스킨을 마친 파일들. 가드가 SCAN_DIRS 로만 순회하면 이 파일들은 검사 대상에서
 * 빠져 색상 리터럴이 조용히 되돌아와도 잡히지 않는다 — 그래서 파일 단위로 명시
 * 등록해 offences() 가 SCAN_DIRS 순회와 별도로 확인하게 한다.
 *
 * Task 8 이 재스킨했지만 보호하지 못하고 남겨둔 두 파일로 시작해, Task 10 이
 * 마이그레이션한 환자접수 화면 파일들을 더한다. Task 11 은 여기에 계속 추가하고,
 * Task 12 는 SCAN_DIRS 를 ["src"] 로 확대하며 이 목록 전체를 걷어낸다.
 */
const SCAN_FILES: string[] = [
  "src/components/Header.module.css",
  "src/components/Sidebar.module.css",
  "src/components/PatientForm.tsx",
  "src/components/PatientForm.module.css",
  "src/components/MedicalInfo.tsx",
  "src/components/MedicalInfo.module.css",
  "src/components/SpecialNote.tsx",
  "src/components/SpecialNote.module.css",
  "src/components/PatientInfoBar.tsx",
  "src/components/PatientInfoBar.module.css",
  "src/components/History.tsx",
  "src/components/HistoryDiagnose.module.css",
  "src/components/ActionBar.tsx",
  "src/components/ActionBar.module.css",
  "src/components/SearchPatientModal.tsx",
  "src/components/SearchPatientModal.module.css",
  "src/components/WaitingStatus.tsx",
  "src/components/WaitingStatus.module.css",
  "src/components/Calender.tsx",
  "src/components/Calender.module.css",
  "src/components/Disease.tsx",
  "src/components/Disease.module.css",
  "src/components/ViewDataBase.tsx",
  "src/components/ViewDataBase.module.css",
];

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
  for (const rel of SCAN_FILES) {
    const absolutePath = join(WEB_ROOT, ...rel.split("/"));
    try {
      found.push(...fileOffences(absolutePath, rel));
    } catch {
      // 파일이 없으면 조용히 건너뛴다 (SCAN_DIRS 순회와 동일한 정책).
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
