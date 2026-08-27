# 프론트엔드 디자인 시스템 재구성 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `apps/web`에 디자인 토큰 레이어와 공용 프리미티브를 도입하고 전 화면을 재스킨해, 라이트/다크 테마가 대비비 테스트로 증명되는 상태를 만든다.

**Architecture:** `src/styles/tokens.css`가 색상 리터럴이 존재하는 유일한 파일이 된다. 원시 램프 → 의미 토큰 → 치수 토큰 3층으로 나누고 컴포넌트는 의미·치수 토큰만 참조한다. 테마는 `<html data-theme>` 속성 + `prefers-color-scheme` 미디어 쿼리 2중 캐스케이드로 처리하며 라이브러리를 추가하지 않는다. 반복 구현된 패널 셸(17곳)과 모달(4곳)을 `src/components/ui/`의 프리미티브로 흡수한 뒤, CSS module 27개를 단계적으로 재작성한다.

**Tech Stack:** Next.js 15.5.4 App Router, React 19.1.0, TypeScript 5, CSS Modules, vitest 4 + jsdom, `@testing-library/react`

**Spec:** `Docs/superpowers/specs/2026-08-27-frontend-design-system-design.md`

---

## Global Constraints

모든 태스크의 요구사항에 아래가 암묵적으로 포함된다.

### GC-1. 시맨틱 보존 (최우선)

DOM의 **요소 종류, ARIA role, 접근성 이름(accessible name), 텍스트 내용**을 바꾸지 않는다. 클래스 이름과 시각 표현은 자유롭게 바꾼다.

근거: `src/components/__tests__/AIReport.test.tsx`가 `findByRole("button", { name: "AI 분석" })`, `findByRole("status")`, `getByText("테스트 경고")`에 의존한다. `data-testid`는 코드베이스 전체에 0건이고 E2E(`tests/e2e/`)는 `httpx` 기반 API 테스트라 DOM과 무관하다.

`<div>`를 `<table>`로 바꾸는 식의 시맨틱 **개선**은 허용한다. 시맨틱을 **없애는** 변경(예: `<button>` → `<div onClick>`)은 금지한다.

### GC-2. 색상 리터럴 금지

`src/styles/tokens.css` 외의 어떤 파일에도 `#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb()`, `rgba()`, `hsl()`, `hsla()`를 쓰지 않는다. `.tsx`의 인라인 `style={{}}`도 포함한다. Task 4가 만드는 가드 테스트가 이를 강제한다.

### GC-3. 원시 램프 직접 참조 금지

컴포넌트 CSS에서 `var(--slate-700)` 같은 원시 램프를 직접 참조하지 않는다. 의미 토큰(`var(--text-secondary)`)만 쓴다. 원시 램프를 직접 쓰면 다크 모드에서 뒤집히지 않는다.

### GC-4. 기존 레이아웃 골격 유지

`grid-template-columns` 값, 반응형 breakpoint(1200 / 1024 / 768 / 640px), 컬럼 구성은 그대로 둔다. 변경 대상은 표면 — 색, 여백, 타이포, 경계, 모서리, 상태 표현.

### GC-5. 밀도 규칙 (A 골격 + B 여백)

- 패널 내부 패딩 `var(--space-4)` (16px)
- 데이터 행 높이 `var(--row-height)` (36px)
- 패널 간 간격 `var(--space-4)`, 패널 내 섹션 간격 `var(--space-3)`
- 그림자는 떠 있는 것(모달, 팝오버, 드롭다운)에만. 평면 표면은 `var(--border)` 헤어라인으로 층을 표현한다.
- 강조색은 화면당 실질 1개. `Button variant="primary"`는 화면당 1개가 원칙.

### GC-6. 테스트 실행

각 태스크 커밋 전 `apps/web`에서 실행한다.

```bash
yarn test
```

기존 통과 테스트가 깨지면 그 태스크는 완료가 아니다.

### GC-7. 레거시 리터럴 → 토큰 매핑표

재스킨 태스크(8~12)는 아래 표를 따른다. 코드베이스의 distinct hex 113종을 전수 추출해 분류한 것이다.

| 기존 리터럴 | 용도 | 토큰 |
|---|---|---|
| `#fff` `#ffffff` `#f9fafb` `#fafafa` `#f8f9ff` `#f7f8fb` `#f5f5f5` `#f0f0f0` | 패널·카드·입력 배경 | `--surface-raised` |
| `#f3f4f6` `#f1f5f9` `#5e5e61` `#f2f2f2` | 페이지 배경 | `--surface-canvas` |
| `#e2e8f0`(배경 용도) `#e5e7eb`(배경 용도) | 우묵한 영역, 테이블 헤더 | `--surface-sunken` |
| `#333336` `#2f2f2f` `#2d2d30` `#1f1f22` `#11131f` `#202833` `#1e293b` `#0a0a0a` `#1a1a1a` `#262626` | 헤더·사이드바 크롬 | `--surface-chrome` |
| `#303032` `#3a3a3d` `#3b3b3b` `#383838` `#334155` | 크롬 내 hover | `--surface-chrome-hover` |
| `#515154` `#434346` `#444444` `#4a4a4a` `#535353` `#555555` `#475569` `#1e3a5f` `#1e4a7a` | 크롬 내 활성 항목 | `--surface-chrome-active` |
| `#111827` `#111` `#171717` `#1f2937` `#2d3748` `#000` `#000000` | 본문 텍스트 | `--text-primary` |
| `#374151` `#4b5563` `#4a5568` `#333` | 보조 텍스트 | `--text-secondary` |
| `#6b7280` `#9ca3af` `#a0aec0` `#64748b` `#666` `#ccc` `#ededed` | 라벨·placeholder·메타데이터 | `--text-muted` |
| `#e5e7eb` `#e2e8f0` `#eee` `#e5e5e5` `#f1f5f9` (구분선 용도) | 장식용 구분선 | `--border` |
| `#d1d5db` `#cbd5e1` (구분선 용도) | 강조 구분선 | `--border-strong` |
| `#ddd` `#d1d5db` `#cbd5e1` (입력·버튼 테두리 용도) | 상호작용 요소 테두리 | `--border-control` |
| `#2563eb` `#3b82f6` `#1d4ed8` `#1565c0` `#0d47a1` `#1a4f8a` `#3182ce` `#4f6bff` | 기본 버튼 배경, 활성 강조 | `--accent-fill` / `--accent-fill-hover` |
| `#60a5fa` `#93c5fd` `#63b3ed` `#9dabff` | 링크·강조 텍스트 | `--accent-text` |
| `#dbeafe` `#d7dcff` `#f1f3ff` `#cbd5f5` `#f8fafc`(선택 행) | 선택 행, 활성 내비 배경 | `--accent-bg` |
| `#7c3aed` `#6d28d9` `#a855f7` `#a78bfa` | AI·에이전트 보라 강조 | `--accent-fill` / `--accent-text` 로 통합. **보라 램프를 도입하지 않는다** |
| `#10b981` `#16a34a` `#059669` `#047857` `#38a169` `#166534` `#365314` `#17200f` | 성공·완료 | `--success-text` |
| `#d1fae5` `#dcfce7` `#cdffee` `#ecfccb` `#d9f99d` | 성공 배경 | `--success-bg` |
| `#f59e0b` `#ffa726` `#f9d14c` `#e8c508` `#ffd700` `#92400e` | 경고 | `--warning-text` |
| `#fef3c7` `#fffbeb` `#fff4e5` `#fde68a` | 경고 배경 | `--warning-bg` |
| `#ef4444` `#dc2626` `#c00` `#f87171` `#ff6b6b` `#ff9b9b` | 위험 버튼·오류 텍스트 | `--danger-fill` / `--danger-text` |
| `#fee2e2` `#fecaca` `#fef2f2` `#991b1b` | 위험 배경·텍스트 | `--danger-bg` / `--danger-text` |
| `rgba(0,0,0,0.1 / 0.3 / 0.35 / 0.45 / 0.55)` | 그림자, 모달 백드롭 | `--shadow-sm/md/lg`, `::backdrop` |
| `rgba(255,255,255,0.04~0.95)` | 크롬 위 반투명 버튼 | `Button variant="ghost"` + `--text-on-chrome` |
| `rgba(59,130,246,*)` `rgba(96,165,250,*)` `rgba(79,107,255,*)` `rgba(241,243,255,*)` `rgba(88,95,137,*)` `rgba(9,12,28,*)` | 강조 글로우·틴트 | `--accent-bg` 또는 `--focus-ring`. 반투명 글로우는 제거한다 |

표에 없는 리터럴을 만나면 **가장 가까운 의미 토큰으로 보내고 태스크 보고서에 기록한다.** 새 토큰을 임의로 추가하지 않는다.

### GC-8. 재스킨 표준 절차

Task 8~12는 파일마다 아래 순서를 따른다.

1. 컴포넌트 `.tsx`를 읽고 **자체 패널 셸**(제목 행 + 본문 래퍼)이 있으면 `Panel`로 교체한다. `title`에는 기존 제목 텍스트를 그대로 넣는다.
2. **목록·격자**가 `<div>`로 되어 있으면 `<table>` + `Table`로 승격한다. 시맨틱 개선이라 GC-1이 허용한다.
3. **상태 문자열**(대기/진료중/완료 등)을 `Badge`로 감싼다.
4. **`position: fixed` 오버레이**가 있으면 `Modal`로 교체한다.
5. **빈 목록 분기**에 `EmptyState`를 넣는다. 분기가 없으면 만든다.
6. `.module.css`를 열어 GC-7 매핑표대로 리터럴을 토큰으로 치환하고, 패딩·간격을 GC-5 스케일로 올린다.
7. 파일에 리터럴이 0인지 grep으로 확인한다.
8. `yarn test`를 돌린다.

**변경 전후로 반드시 같아야 하는 것:** 요소 종류, `role`, 접근성 이름, 화면에 보이는 텍스트(GC-1).

#### 완성 예제 — 패널 셸 이관

전형적인 기존 코드:

```tsx
// before
<div className={styles.container}>
  <div className={styles.header}>
    <span className={styles.title}>대기 현황</span>
    <button className={styles.refreshBtn} onClick={reload}>새로고침</button>
  </div>
  <div className={styles.body}>
    {rows.map((row) => (
      <div key={row.id} className={styles.row} onClick={() => select(row)}>
        <span>{row.name}</span>
        <span className={styles.stateWaiting}>{row.state}</span>
      </div>
    ))}
  </div>
</div>
```

```css
/* before */
.container { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
.header { padding: 8px 12px; background: #f3f4f6; border-bottom: 1px solid #e5e7eb; }
.title { font-size: 13px; color: #374151; font-weight: 600; }
.refreshBtn { background: #2563eb; color: #fff; border: 0; padding: 4px 8px; border-radius: 4px; }
.row { display: flex; justify-content: space-between; padding: 6px 12px; }
.row:hover { background: #f3f4f6; }
.stateWaiting { background: #dbeafe; color: #1d4ed8; font-size: 12px; padding: 1px 6px; }
```

이관 후:

```tsx
// after
import { Badge, Button, EmptyState, Panel, Table } from "@/components/ui";
import styles from "./WaitingStatus.module.css";

<Panel
  title="대기 현황"
  padding="none"
  actions={
    <Button size="sm" onClick={reload}>
      새로고침
    </Button>
  }
>
  {rows.length === 0 ? (
    <EmptyState title="대기 중인 환자가 없습니다" />
  ) : (
    <Table stickyHeader>
      <thead>
        <tr>
          <th scope="col">환자명</th>
          <th scope="col">상태</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.id}
            aria-selected={row.id === selectedId}
            onClick={() => select(row)}
            className={styles.row}
          >
            <td>{row.name}</td>
            <td>
              <Badge tone={TONE_BY_STATE[row.state]}>{row.state}</Badge>
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  )}
</Panel>
```

```css
/* after — 남는 것은 이 컴포넌트에만 있는 규칙뿐이다 */
.row {
  cursor: pointer;
}
```

```ts
// 상태 -> tone 매핑은 spec §4.2 를 따른다.
const TONE_BY_STATE = {
  waiting: "accent",
  inProgress: "warning",
  done: "success",
  cancelled: "danger",
} as const;
```

**핵심:** 이관이 끝나면 `.module.css`가 대부분 비어야 정상이다. 패널 셸, 행 높이, 경계선, 배지 색은 전부 프리미티브가 갖고 있다. CSS가 여전히 50줄 넘게 남았다면 프리미티브로 흡수할 수 있는 규칙을 놓친 것이다.

---

## File Structure

| 경로 | 책임 |
|---|---|
| `src/styles/tokens.css` | 원시 램프 + 의미 토큰 + 치수 토큰. 색상 리터럴의 유일한 거처 |
| `src/styles/reset.css` | 박스 모델, 마진 초기화, 포커스 가시성 |
| `src/styles/__tests__/contrast.test.ts` | `tokens.css` 파싱 + WCAG 대비비 단언 |
| `src/styles/__tests__/no-hardcoded-color.test.ts` | 색상 리터럴 가드 |
| `src/app/globals.css` | 토큰 import + body 타이포 + 전역 폼 컨트롤 스타일 |
| `src/app/theme-script.ts` | hydration 이전 실행 스크립트 문자열 |
| `src/app/layout.tsx` | `lang="ko"`, metadata, 폰트 변수, 테마 부트 스크립트 |
| `src/app/styleguide/page.tsx` | 개발 전용 프리미티브 카탈로그 |
| `src/components/theme/ThemeProvider.tsx` | 테마 상태 컨텍스트 |
| `src/components/ui/Panel.{tsx,module.css}` | 패널 셸 |
| `src/components/ui/Button.{tsx,module.css}` | 버튼 4 variant |
| `src/components/ui/Badge.{tsx,module.css}` | 상태 배지 5 tone |
| `src/components/ui/EmptyState.{tsx,module.css}` | 빈 상태 |
| `src/components/ui/Field.{tsx,module.css}` | 라벨 + 오류 + 힌트 래퍼 |
| `src/components/ui/Table.{tsx,module.css}` | 데이터 테이블 |
| `src/components/ui/Modal.{tsx,module.css}` | `<dialog>` 기반 모달 |
| `src/components/ui/ThemeToggle.{tsx,module.css}` | 3상태 테마 토글 |
| `src/components/ui/index.ts` | 배럴 export |

---

## Task 개요

| # | 내용 | 결과물 |
|---|---|---|
| 1 | 대비비 테스트 + `tokens.css` | 토큰이 존재하고 대비가 증명됨 |
| 2 | `reset.css` + `globals.css` + `layout.tsx` | 폰트·metadata·`lang` 정상화, 스타터 잔재 제거 |
| 3 | `ThemeProvider` + `ThemeToggle` + 부트 스크립트 | 테마 3상태 전환 동작 |
| 4 | 하드코딩 가드 테스트 | 회귀 차단 장치 |
| 5 | 프리미티브 A — `Panel` `Button` `Badge` `EmptyState` | |
| 6 | 프리미티브 B — `Field` `Table` `Modal` + 전역 폼 스타일 | |
| 7 | `/styleguide` | 기준 화면 |
| 8 | 앱 셸 재스킨 | `BitComputer EMR`, 실제 사용자명, 관리자 헤더 통일 |
| 9 | 인증 화면 재스킨 | 인라인 스타일 제거 |
| 10 | 환자접수 화면 재스킨 | |
| 11 | 진료실 화면 재스킨 | |
| 12 | 진단서·기타 재스킨 + 가드 전체 확대 | GC-2 전면 적용 |

---

### Task 1: 대비비 테스트와 토큰 레이어

**Files:**
- Create: `apps/web/src/styles/__tests__/contrast.test.ts`
- Create: `apps/web/src/styles/tokens.css`

**Interfaces:**
- Produces: `tokens.css`가 정의하는 의미·치수 토큰 전체. 이후 모든 태스크가 이 이름들을 참조한다.
- Produces: `tokens.css`의 블록 구조 — `:root {`, `@media (prefers-color-scheme: dark) {`, `:root[data-theme="dark"] {` 세 마커. 테스트가 이 문자열을 그대로 찾으므로 형식을 바꾸지 않는다.

**주의:** `vitest.config.ts`의 `include`가 `src/**/*.test.{ts,tsx}`이므로 파일명이 `.test.ts`여야 한다. 테스트는 `tokens.css`를 **import 하지 않고** `node:fs`로 읽는다(vitest에 CSS 처리 설정이 없다).

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/web/src/styles/__tests__/contrast.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const TOKENS_PATH = resolve(__dirname, "../tokens.css");
const css = readFileSync(TOKENS_PATH, "utf8");

const LIGHT_MARKER = ":root {";
const MEDIA_MARKER = "@media (prefers-color-scheme: dark) {";
const DARK_MARKER = ':root[data-theme="dark"] {';

/** marker 뒤 첫 `{` 부터 짝이 맞는 `}` 까지의 본문을 돌려준다. */
function blockAfter(source: string, marker: string): string {
  const start = source.indexOf(marker);
  if (start === -1) {
    throw new Error(`tokens.css 에서 마커를 찾지 못했습니다: ${marker}`);
  }
  const open = source.indexOf("{", start + marker.length - 1);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open + 1, i);
    }
  }
  throw new Error(`블록이 닫히지 않았습니다: ${marker}`);
}

function declarations(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /--([\w-]+)\s*:\s*([^;]+);/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(block)) !== null) {
    out[m[1]] = m[2].trim();
  }
  return out;
}

const lightDecls = declarations(blockAfter(css, LIGHT_MARKER));
const mediaDecls = declarations(blockAfter(css, MEDIA_MARKER));
const darkDecls = declarations(blockAfter(css, DARK_MARKER));

/** `var(--x)` 를 원시 램프(:root 에만 존재)까지 따라가 hex 로 만든다. */
function resolveToken(themeDecls: Record<string, string>, name: string, depth = 0): string {
  if (depth > 5) throw new Error(`토큰 참조가 너무 깊습니다: --${name}`);
  const raw = themeDecls[name] ?? lightDecls[name];
  if (raw === undefined) throw new Error(`정의되지 않은 토큰: --${name}`);
  const ref = /^var\(\s*--([\w-]+)\s*\)$/.exec(raw);
  if (ref) return resolveToken(lightDecls, ref[1], depth + 1);
  if (!/^#[0-9a-fA-F]{6}$/.test(raw)) {
    throw new Error(`hex 로 해석되지 않는 토큰: --${name} = ${raw}`);
  }
  return raw;
}

function relativeLuminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const linear = channels.map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  );
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

/** [전경, 배경, 최소대비] */
const PAIRS: Array<[string, string, number]> = [
  ["text-primary", "surface-canvas", 4.5],
  ["text-primary", "surface-raised", 4.5],
  ["text-primary", "surface-sunken", 4.5],
  ["text-primary", "surface-overlay", 4.5],
  ["text-secondary", "surface-raised", 4.5],
  ["text-secondary", "surface-canvas", 4.5],
  ["text-muted", "surface-raised", 4.5],
  ["text-muted", "surface-canvas", 4.5],
  ["text-on-chrome", "surface-chrome", 4.5],
  ["text-on-chrome", "surface-chrome-hover", 4.5],
  ["text-on-chrome", "surface-chrome-active", 4.5],
  ["text-on-fill", "accent-fill", 4.5],
  ["text-on-fill", "danger-fill", 4.5],
  ["accent-text", "surface-raised", 4.5],
  ["accent-text", "accent-bg", 4.5],
  ["success-text", "success-bg", 4.5],
  ["warning-text", "warning-bg", 4.5],
  ["danger-text", "danger-bg", 4.5],
  ["border-control", "surface-raised", 3.0],
  ["border-control", "surface-canvas", 3.0],
  ["focus-ring", "surface-raised", 3.0],
  ["focus-ring", "surface-canvas", 3.0],
];

const THEMES: Array<[string, Record<string, string>]> = [
  ["light", lightDecls],
  ["dark", darkDecls],
];

describe("디자인 토큰 대비비", () => {
  for (const [themeName, decls] of THEMES) {
    for (const [fg, bg, min] of PAIRS) {
      it(`${themeName}: --${fg} on --${bg} >= ${min}:1`, () => {
        const ratio = contrastRatio(resolveToken(decls, fg), resolveToken(decls, bg));
        expect(ratio).toBeGreaterThanOrEqual(min);
      });
    }
  }
});

describe("다크 토큰 두 블록 일치", () => {
  it("미디어 쿼리 블록과 [data-theme=dark] 블록이 같은 토큰을 같은 값으로 선언한다", () => {
    expect(Object.keys(mediaDecls).sort()).toEqual(Object.keys(darkDecls).sort());
    for (const key of Object.keys(darkDecls)) {
      expect(`${key}=${mediaDecls[key]}`).toBe(`${key}=${darkDecls[key]}`);
    }
  });

  it("다크 블록이 라이트에 있는 의미 토큰을 빠짐없이 재정의한다", () => {
    const semantic = Object.keys(lightDecls).filter((k) => lightDecls[k].startsWith("var("));
    const missing = semantic.filter((k) => !(k in darkDecls));
    expect(missing).toEqual([]);
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/web && yarn test src/styles/__tests__/contrast.test.ts
```

기대: `ENOENT` — `tokens.css`가 없어서 실패.

- [ ] **Step 3: `tokens.css` 작성**

**형식 규칙:** 의미 토큰은 반드시 `var(--원시램프)` 형태로만 쓴다(테스트의 "다크 블록 누락" 검사가 이 형태를 기준으로 의미 토큰을 식별한다). 원시 램프는 `:root` 블록에만 두고 다크 블록에서 재정의하지 않는다.

`apps/web/src/styles/tokens.css`:

```css
:root {
  --slate-50: #f8fafc;
  --slate-100: #f1f5f9;
  --slate-200: #e2e8f0;
  --slate-300: #cbd5e1;
  --slate-400: #94a3b8;
  --slate-500: #64748b;
  --slate-600: #475569;
  --slate-700: #334155;
  --slate-800: #1e293b;
  --slate-900: #0f172a;
  --slate-950: #020617;
  --white: #ffffff;
  --overlay-dark: #293548;

  --blue-100: #dbeafe;
  --blue-400: #60a5fa;
  --blue-600: #2563eb;
  --blue-700: #1d4ed8;
  --blue-950: #172554;

  --green-100: #dcfce7;
  --green-300: #86efac;
  --green-800: #166534;
  --green-950: #14532d;

  --amber-100: #fef3c7;
  --amber-300: #fcd34d;
  --amber-800: #92400e;
  --amber-950: #451a03;

  --red-100: #fee2e2;
  --red-300: #fca5a5;
  --red-600: #dc2626;
  --red-800: #991b1b;
  --red-950: #450a0a;

  color-scheme: light;

  --surface-canvas: var(--slate-100);
  --surface-sunken: var(--slate-200);
  --surface-raised: var(--white);
  --surface-overlay: var(--white);
  --surface-chrome: var(--slate-900);
  --surface-chrome-hover: var(--slate-800);
  --surface-chrome-active: var(--slate-700);

  --text-primary: var(--slate-900);
  --text-secondary: var(--slate-700);
  --text-muted: var(--slate-600);
  --text-on-chrome: var(--slate-200);
  --text-on-fill: var(--white);

  --border: var(--slate-200);
  --border-strong: var(--slate-300);
  --border-control: var(--slate-500);

  --accent-fill: var(--blue-600);
  --accent-fill-hover: var(--blue-700);
  --accent-text: var(--blue-700);
  --accent-bg: var(--blue-100);
  --focus-ring: var(--blue-600);

  --success-bg: var(--green-100);
  --success-text: var(--green-800);
  --warning-bg: var(--amber-100);
  --warning-text: var(--amber-800);
  --danger-bg: var(--red-100);
  --danger-text: var(--red-800);
  --danger-fill: var(--red-600);

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;

  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 10px;
  --radius-full: 999px;

  --font-size-xs: 12px;
  --line-height-xs: 1.5;
  --font-size-sm: 13px;
  --line-height-sm: 1.55;
  --font-size-base: 14px;
  --line-height-base: 1.6;
  --font-size-lg: 16px;
  --line-height-lg: 1.5;
  --font-size-xl: 20px;
  --line-height-xl: 1.4;

  --row-height: 36px;
  --control-height: 36px;
  --control-height-sm: 30px;

  --shadow-sm: 0 1px 2px rgb(15 23 42 / 0.06);
  --shadow-md: 0 4px 12px rgb(15 23 42 / 0.1);
  --shadow-lg: 0 12px 32px rgb(15 23 42 / 0.16);
  --backdrop: rgb(15 23 42 / 0.45);

  --dur-fast: 120ms;
  --dur-base: 200ms;
  --ease: cubic-bezier(0.2, 0, 0, 1);

  --font-sans: var(--font-geist-sans), "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  --font-mono: var(--font-geist-mono), "D2Coding", ui-monospace, monospace;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;

    --surface-canvas: var(--slate-900);
    --surface-sunken: var(--slate-950);
    --surface-raised: var(--slate-800);
    --surface-overlay: var(--overlay-dark);
    --surface-chrome: var(--slate-950);
    --surface-chrome-hover: var(--slate-900);
    --surface-chrome-active: var(--slate-800);

    --text-primary: var(--slate-100);
    --text-secondary: var(--slate-300);
    --text-muted: var(--slate-400);
    --text-on-chrome: var(--slate-200);
    --text-on-fill: var(--white);

    --border: var(--slate-700);
    --border-strong: var(--slate-600);
    --border-control: var(--slate-400);

    --accent-fill: var(--blue-600);
    --accent-fill-hover: var(--blue-700);
    --accent-text: var(--blue-400);
    --accent-bg: var(--blue-950);
    --focus-ring: var(--blue-400);

    --success-bg: var(--green-950);
    --success-text: var(--green-300);
    --warning-bg: var(--amber-950);
    --warning-text: var(--amber-300);
    --danger-bg: var(--red-950);
    --danger-text: var(--red-300);
    --danger-fill: var(--red-600);

    --shadow-sm: 0 1px 2px rgb(2 6 23 / 0.3);
    --shadow-md: 0 4px 12px rgb(2 6 23 / 0.4);
    --shadow-lg: 0 12px 32px rgb(2 6 23 / 0.55);
    --backdrop: rgb(2 6 23 / 0.65);

    --font-sans: var(--font-geist-sans), "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    --font-mono: var(--font-geist-mono), "D2Coding", ui-monospace, monospace;
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;

  --surface-canvas: var(--slate-900);
  --surface-sunken: var(--slate-950);
  --surface-raised: var(--slate-800);
  --surface-overlay: var(--overlay-dark);
  --surface-chrome: var(--slate-950);
  --surface-chrome-hover: var(--slate-900);
  --surface-chrome-active: var(--slate-800);

  --text-primary: var(--slate-100);
  --text-secondary: var(--slate-300);
  --text-muted: var(--slate-400);
  --text-on-chrome: var(--slate-200);
  --text-on-fill: var(--white);

  --border: var(--slate-700);
  --border-strong: var(--slate-600);
  --border-control: var(--slate-400);

  --accent-fill: var(--blue-600);
  --accent-fill-hover: var(--blue-700);
  --accent-text: var(--blue-400);
  --accent-bg: var(--blue-950);
  --focus-ring: var(--blue-400);

  --success-bg: var(--green-950);
  --success-text: var(--green-300);
  --warning-bg: var(--amber-950);
  --warning-text: var(--amber-300);
  --danger-bg: var(--red-950);
  --danger-text: var(--red-300);
  --danger-fill: var(--red-600);

  --shadow-sm: 0 1px 2px rgb(2 6 23 / 0.3);
  --shadow-md: 0 4px 12px rgb(2 6 23 / 0.4);
  --shadow-lg: 0 12px 32px rgb(2 6 23 / 0.55);
  --backdrop: rgb(2 6 23 / 0.65);

  --font-sans: var(--font-geist-sans), "Pretendard Variable", Pretendard, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  --font-mono: var(--font-geist-mono), "D2Coding", ui-monospace, monospace;
}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd apps/web && yarn test src/styles/__tests__/contrast.test.ts
```

기대: 46개 통과(대비 쌍 22 × 테마 2 + 일치 검사 2), 실패 0.

만약 어떤 쌍이 실패하면 **토큰 stop을 조정해서 통과시킨다.** 테스트의 최소값을 낮추지 않는다.

- [ ] **Step 5: 커밋**

```bash
git add apps/web/src/styles
git commit -m "feat(web): 디자인 토큰 레이어와 대비비 테스트 추가"
```

---

### Task 2: reset, globals, layout 정상화

**Files:**
- Create: `apps/web/src/styles/reset.css`
- Modify: `apps/web/src/app/globals.css` (전면 재작성)
- Modify: `apps/web/src/app/layout.tsx`
- Delete: `apps/web/src/app/page.module.css`

**Interfaces:**
- Consumes: Task 1의 토큰 전체
- Produces: `body`가 `--font-sans`/`--surface-canvas`/`--text-primary`를 실제로 적용한 상태. 전역 `:focus-visible` 스타일.

**배경:** 현재 `globals.css`의 `body`가 `font-family: Arial, Helvetica`로 `--font-geist-sans`를 덮고 있어 로드한 폰트가 적용된 적이 없다. `layout.tsx`의 metadata는 `"Create Next App"`, `lang`은 `"en"`이다. `src/app/page.module.css`(199줄)는 루트 `page.tsx`가 `return null`이라 죽은 코드다.

- [ ] **Step 1: `reset.css` 작성**

`apps/web/src/styles/reset.css`:

```css
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html,
body {
  max-width: 100vw;
  overflow-x: hidden;
}

a {
  color: inherit;
  text-decoration: none;
}

button {
  font: inherit;
  color: inherit;
}

:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

:focus:not(:focus-visible) {
  outline: none;
}
```

- [ ] **Step 2: `globals.css` 전면 재작성**

`apps/web/src/app/globals.css`:

```css
@import "../styles/tokens.css";
@import "../styles/reset.css";

body {
  background: var(--surface-canvas);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

input,
select,
textarea {
  height: var(--control-height);
  padding: 0 var(--space-3);
  border: 1px solid var(--border-control);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  color: var(--text-primary);
  font-family: inherit;
  font-size: var(--font-size-base);
  transition: border-color var(--dur-fast) var(--ease);
}

textarea {
  height: auto;
  min-height: calc(var(--control-height) * 2);
  padding: var(--space-2) var(--space-3);
  line-height: var(--line-height-base);
  resize: vertical;
}

input::placeholder,
textarea::placeholder {
  color: var(--text-muted);
}

input:hover:not(:disabled),
select:hover:not(:disabled),
textarea:hover:not(:disabled) {
  border-color: var(--accent-fill);
}

input:disabled,
select:disabled,
textarea:disabled {
  background: var(--surface-sunken);
  color: var(--text-muted);
  cursor: not-allowed;
}

table {
  border-collapse: collapse;
}
```

**주의:** `@import`는 CSS 파일 최상단에 있어야 한다. 위에 어떤 규칙도 두지 않는다.

- [ ] **Step 3: 죽은 스타터 CSS 삭제**

```bash
cd apps/web && rm src/app/page.module.css
grep -rn "page.module.css" src || echo "참조 없음"
```

기대: "참조 없음". 루트 `src/app/page.tsx`는 `return null`이므로 import가 없다.

- [ ] **Step 4: `layout.tsx` 수정**

`apps/web/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import ClientProviders from "./ClientProviders";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BitComputer EMR",
  description: "AI 보조 진료 기록 시스템",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable}`} suppressHydrationWarning>
        <ClientProviders>{children}</ClientProviders>
      </body>
    </html>
  );
}
```

`suppressHydrationWarning`을 `<html>`에도 붙인다. Task 3의 부트 스크립트가 서버 렌더 결과에 없는 `data-theme` 속성을 추가하기 때문이다.

- [ ] **Step 5: 빌드와 테스트 확인**

```bash
cd apps/web && yarn test && yarn build
```

기대: 테스트 전부 통과, 빌드 성공.

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src/app apps/web/src/styles
git commit -m "feat(web): 전역 스타일을 토큰 기반으로 재작성하고 스타터 잔재 제거"
```

---

### Task 3: 테마 상태와 토글

**Files:**
- Create: `apps/web/src/app/theme-script.ts`
- Create: `apps/web/src/components/theme/ThemeProvider.tsx`
- Create: `apps/web/src/components/ui/ThemeToggle.tsx`
- Create: `apps/web/src/components/ui/ThemeToggle.module.css`
- Create: `apps/web/src/components/theme/__tests__/ThemeProvider.test.tsx`
- Modify: `apps/web/src/app/layout.tsx`
- Modify: `apps/web/src/app/ClientProviders.tsx`

**Interfaces:**
- Produces: `useTheme(): { theme: ThemeChoice; setTheme: (t: ThemeChoice) => void }`, `type ThemeChoice = "system" | "light" | "dark"`
- Produces: `<ThemeToggle />` — props 없음. Task 8의 `Header`가 이것을 배치한다.
- Produces: `THEME_STORAGE_KEY = "theme"`, `themeScript: string`

**계약:** `localStorage`에는 `"light"` 또는 `"dark"`만 저장한다. `"system"`은 **키 삭제**로 표현하고 `data-theme` 속성도 제거한다. 이것이 §5.1 캐스케이드가 성립하는 전제다.

- [ ] **Step 1: 부트 스크립트 작성**

`apps/web/src/app/theme-script.ts`:

```ts
export const THEME_STORAGE_KEY = "theme";

/**
 * hydration 이전에 동기 실행되어 저장된 테마를 <html> 에 반영한다.
 * 저장값이 없으면 아무 속성도 붙이지 않는다 — prefers-color-scheme 경로가 처리한다.
 * localStorage 접근이 throw 하는 브라우저(프라이빗 모드)를 위해 try/catch 로 감싼다.
 */
export const themeScript = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t);}catch(e){}})()`;
```

- [ ] **Step 2: 실패하는 테스트 작성**

`apps/web/src/components/theme/__tests__/ThemeProvider.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import ThemeProvider from "../ThemeProvider";
import ThemeToggle from "@/components/ui/ThemeToggle";
import { THEME_STORAGE_KEY } from "@/app/theme-script";

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>
  );
}

describe("ThemeProvider / ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("저장값이 없으면 system 상태로 시작하고 data-theme 속성을 붙이지 않는다", () => {
    renderToggle();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("저장된 dark 를 복원한다", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderToggle();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("system -> light -> dark -> system 을 순환한다", () => {
    renderToggle();
    const button = screen.getByRole("button");

    fireEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");

    fireEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    fireEvent.click(button);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it("현재 상태를 aria-label 로 노출한다", () => {
    renderToggle();
    expect(screen.getByRole("button").getAttribute("aria-label")).toContain("시스템");
  });
});
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```bash
cd apps/web && yarn test src/components/theme
```

기대: 모듈을 찾을 수 없어 실패.

- [ ] **Step 4: `ThemeProvider` 구현**

`apps/web/src/components/theme/ThemeProvider.tsx`:

```tsx
"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { THEME_STORAGE_KEY } from "@/app/theme-script";

export type ThemeChoice = "system" | "light" | "dark";

interface ThemeContextValue {
  theme: ThemeChoice;
  setTheme: (next: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredTheme(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function applyTheme(next: ThemeChoice) {
  const root = document.documentElement;
  if (next === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", next);
  }
}

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeChoice>("system");

  // 서버 렌더에는 localStorage 가 없다. 마운트 후 실제 값으로 맞춘다.
  useEffect(() => {
    const stored = readStoredTheme();
    setThemeState(stored);
    applyTheme(stored);
  }, []);

  const setTheme = useCallback((next: ThemeChoice) => {
    setThemeState(next);
    applyTheme(next);
    try {
      if (next === "system") {
        localStorage.removeItem(THEME_STORAGE_KEY);
      } else {
        localStorage.setItem(THEME_STORAGE_KEY, next);
      }
    } catch {
      // 저장에 실패해도 이번 세션의 화면은 이미 바뀌었다.
    }
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme 은 ThemeProvider 안에서만 쓸 수 있습니다.");
  }
  return ctx;
}
```

- [ ] **Step 5: `ThemeToggle` 구현**

`apps/web/src/components/ui/ThemeToggle.tsx`:

```tsx
"use client";

import { useTheme, type ThemeChoice } from "@/components/theme/ThemeProvider";
import styles from "./ThemeToggle.module.css";

const ORDER: ThemeChoice[] = ["system", "light", "dark"];

const LABEL: Record<ThemeChoice, string> = {
  system: "시스템 설정",
  light: "라이트",
  dark: "다크",
};

function nextOf(current: ThemeChoice): ThemeChoice {
  return ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
}

function Icon({ theme }: { theme: ThemeChoice }) {
  if (theme === "light") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
      </svg>
    );
  }
  if (theme === "dark") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M8 21h8" />
    </svg>
  );
}

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = nextOf(theme);

  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={() => setTheme(next)}
      aria-label={`테마: ${LABEL[theme]}. 클릭하면 ${LABEL[next]}`}
    >
      <Icon theme={theme} />
    </button>
  );
}
```

`apps/web/src/components/ui/ThemeToggle.module.css`:

```css
.toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--control-height-sm);
  height: var(--control-height-sm);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: inherit;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease);
}

.toggle:hover {
  background: var(--surface-chrome-hover);
  border-color: var(--border-strong);
}
```

- [ ] **Step 6: Provider 연결과 부트 스크립트 주입**

`apps/web/src/app/ClientProviders.tsx`:

```tsx
"use client";

import ThemeProvider from "@/components/theme/ThemeProvider";

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}
```

`layout.tsx`의 `<html>` 안, `<body>` 앞에 스크립트를 넣는다. import 두 줄과 `<head>` 블록만 추가하고 나머지는 Task 2 상태를 유지한다:

```tsx
import { themeScript } from "./theme-script";

// ... 컴포넌트 안
    <html lang="ko" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable}`} suppressHydrationWarning>
        <ClientProviders>{children}</ClientProviders>
      </body>
    </html>
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
cd apps/web && yarn test && yarn build
```

기대: `ThemeProvider.test.tsx` 4개 포함 전부 통과.

- [ ] **Step 8: 커밋**

```bash
git add apps/web/src
git commit -m "feat(web): 의존성 없는 3상태 테마 전환 구현"
```

---

### Task 4: 하드코딩 색상 가드 테스트

**Files:**
- Create: `apps/web/src/styles/__tests__/no-hardcoded-color.test.ts`

**Interfaces:**
- Produces: `SCAN_DIRS` 상수. Task 12가 이 배열을 `["src"]`로 확대한다.

**배경:** 규칙을 문서로만 남기면 다음 사람이 지키지 않는다. 이 테스트가 GC-2를 강제한다. 스캔 범위는 재스킨이 끝난 영역만 포함하고 Task 12에서 전체로 넓힌다 — 처음부터 전체로 켜면 항상 실패하는 테스트가 된다.

- [ ] **Step 1: 테스트 작성**

`apps/web/src/styles/__tests__/no-hardcoded-color.test.ts`:

```ts
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
```

- [ ] **Step 2: 테스트 실행**

```bash
cd apps/web && yarn test src/styles/__tests__/no-hardcoded-color.test.ts
```

기대: 통과. Task 1~3이 만든 파일은 이미 토큰만 쓴다.

**실패하면** 보고된 파일의 리터럴을 GC-7 매핑표에 따라 토큰으로 바꾼다. 테스트를 느슨하게 만들지 않는다.

- [ ] **Step 3: 커밋**

```bash
git add apps/web/src/styles/__tests__/no-hardcoded-color.test.ts
git commit -m "test(web): tokens.css 밖 색상 리터럴 금지 가드 추가"
```

---

### Task 5: 프리미티브 A — Panel, Button, Badge, EmptyState

**Files:**
- Create: `apps/web/src/components/ui/Panel.tsx`, `Panel.module.css`
- Create: `apps/web/src/components/ui/Button.tsx`, `Button.module.css`
- Create: `apps/web/src/components/ui/Badge.tsx`, `Badge.module.css`
- Create: `apps/web/src/components/ui/EmptyState.tsx`, `EmptyState.module.css`
- Create: `apps/web/src/components/ui/index.ts`
- Create: `apps/web/src/components/ui/__tests__/primitives.test.tsx`

**Interfaces:**
- Produces:
  ```ts
  Panel: { title?: ReactNode; actions?: ReactNode; footer?: ReactNode;
           padding?: "none" | "md"; className?: string; children: ReactNode }
  Button: { variant?: "primary" | "secondary" | "ghost" | "danger";
            size?: "sm" | "md"; loading?: boolean }
          & ButtonHTMLAttributes<HTMLButtonElement>
  Badge:  { tone?: "neutral" | "accent" | "success" | "warning" | "danger";
            children: ReactNode }
  EmptyState: { title: string; description?: string; action?: ReactNode }
  ```
- Produces: `src/components/ui/index.ts`가 `Panel`, `Button`, `Badge`, `EmptyState`, `ThemeToggle`을 named export 한다. Task 6이 여기에 `Field`, `Table`, `Modal`을 추가한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/web/src/components/ui/__tests__/primitives.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Badge, Button, EmptyState, Panel } from "../index";

describe("Panel", () => {
  it("title 을 헤딩으로 렌더한다", () => {
    render(<Panel title="대기 현황">본문</Panel>);
    expect(screen.getByRole("heading", { name: "대기 현황" })).toBeInTheDocument();
    expect(screen.getByText("본문")).toBeInTheDocument();
  });

  it("title 이 없으면 헤딩을 만들지 않는다", () => {
    render(<Panel>본문만</Panel>);
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("actions 를 렌더한다", () => {
    render(<Panel title="목록" actions={<button type="button">추가</button>}>본문</Panel>);
    expect(screen.getByRole("button", { name: "추가" })).toBeInTheDocument();
  });
});

describe("Button", () => {
  it("type 기본값이 button 이다", () => {
    render(<Button>저장</Button>);
    expect(screen.getByRole("button", { name: "저장" })).toHaveAttribute("type", "button");
  });

  it("loading 이면 비활성이고 접근성 이름을 유지한다", () => {
    render(<Button loading>분석</Button>);
    const button = screen.getByRole("button", { name: "분석" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("전달한 type 을 덮어쓰지 않는다", () => {
    render(<Button type="submit">제출</Button>);
    expect(screen.getByRole("button", { name: "제출" })).toHaveAttribute("type", "submit");
  });
});

describe("Badge", () => {
  it("내용을 렌더한다", () => {
    render(<Badge tone="warning">stub</Badge>);
    expect(screen.getByText("stub")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("title 과 description 을 렌더한다", () => {
    render(<EmptyState title="내역이 없습니다" description="환자를 먼저 선택하세요" />);
    expect(screen.getByText("내역이 없습니다")).toBeInTheDocument();
    expect(screen.getByText("환자를 먼저 선택하세요")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/web && yarn test src/components/ui
```

기대: `../index`를 찾을 수 없어 실패.

- [ ] **Step 3: `Panel` 구현**

`apps/web/src/components/ui/Panel.tsx`:

```tsx
import styles from "./Panel.module.css";

interface PanelProps {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  footer?: React.ReactNode;
  padding?: "none" | "md";
  className?: string;
  children: React.ReactNode;
}

export default function Panel({
  title,
  actions,
  footer,
  padding = "md",
  className,
  children,
}: PanelProps) {
  return (
    <section className={[styles.panel, className].filter(Boolean).join(" ")}>
      {(title || actions) && (
        <div className={styles.header}>
          {title && <h2 className={styles.title}>{title}</h2>}
          {actions && <div className={styles.actions}>{actions}</div>}
        </div>
      )}
      <div className={padding === "none" ? styles.bodyFlush : styles.body}>{children}</div>
      {footer && <div className={styles.footer}>{footer}</div>}
    </section>
  );
}
```

`apps/web/src/components/ui/Panel.module.css`:

```css
.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-raised);
  overflow: hidden;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
}

.title {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 600;
  line-height: var(--line-height-sm);
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.body {
  flex: 1;
  min-height: 0;
  padding: var(--space-4);
  overflow: auto;
}

.bodyFlush {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.footer {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border);
}
```

- [ ] **Step 4: `Button` 구현**

`apps/web/src/components/ui/Button.tsx`:

```tsx
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: styles.primary,
  secondary: styles.secondary,
  ghost: styles.ghost,
  danger: styles.danger,
};

const SIZE_CLASS: Record<Size, string> = {
  sm: styles.sm,
  md: styles.md,
};

export default function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  disabled,
  className,
  type,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      // type 을 명시하지 않으면 폼 안에서 의도치 않게 submit 된다.
      type={type ?? "button"}
      className={[styles.button, VARIANT_CLASS[variant], SIZE_CLASS[size], className]
        .filter(Boolean)
        .join(" ")}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className={styles.spinner} aria-hidden="true" />}
      {children}
    </button>
  );
}
```

`apps/web/src/components/ui/Button.module.css`:

```css
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-family: inherit;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
}

.button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.md {
  height: var(--control-height);
  padding: 0 var(--space-4);
  font-size: var(--font-size-base);
}

.sm {
  height: var(--control-height-sm);
  padding: 0 var(--space-3);
  font-size: var(--font-size-sm);
}

.primary {
  background: var(--accent-fill);
  color: var(--text-on-fill);
}

.primary:hover:not(:disabled) {
  background: var(--accent-fill-hover);
}

.secondary {
  border-color: var(--border-control);
  background: transparent;
  color: var(--text-primary);
}

.secondary:hover:not(:disabled) {
  background: var(--accent-bg);
  border-color: var(--accent-fill);
}

.ghost {
  background: transparent;
  color: inherit;
}

.ghost:hover:not(:disabled) {
  background: var(--accent-bg);
}

.danger {
  background: var(--danger-fill);
  color: var(--text-on-fill);
}

.danger:hover:not(:disabled) {
  filter: brightness(0.92);
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: var(--radius-full);
  animation: spin 700ms linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}
```

- [ ] **Step 5: `Badge` 구현**

`apps/web/src/components/ui/Badge.tsx`:

```tsx
import styles from "./Badge.module.css";

type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

const TONE_CLASS: Record<Tone, string> = {
  neutral: styles.neutral,
  accent: styles.accent,
  success: styles.success,
  warning: styles.warning,
  danger: styles.danger,
};

export default function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: React.ReactNode;
}) {
  return <span className={`${styles.badge} ${TONE_CLASS[tone]}`}>{children}</span>;
}
```

`apps/web/src/components/ui/Badge.module.css`:

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-weight: 500;
  line-height: var(--line-height-xs);
  white-space: nowrap;
}

.neutral {
  background: var(--surface-sunken);
  color: var(--text-secondary);
}

.accent {
  background: var(--accent-bg);
  color: var(--accent-text);
}

.success {
  background: var(--success-bg);
  color: var(--success-text);
}

.warning {
  background: var(--warning-bg);
  color: var(--warning-text);
}

.danger {
  background: var(--danger-bg);
  color: var(--danger-text);
}
```

- [ ] **Step 6: `EmptyState` 구현**

`apps/web/src/components/ui/EmptyState.tsx`:

```tsx
import styles from "./EmptyState.module.css";

export default function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className={styles.empty}>
      <p className={styles.title}>{title}</p>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
```

`apps/web/src/components/ui/EmptyState.module.css`:

```css
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.title {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-base);
}

.description {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--font-size-sm);
}

.action {
  margin-top: var(--space-2);
}
```

- [ ] **Step 7: 배럴 작성**

`apps/web/src/components/ui/index.ts`:

```ts
export { default as Badge } from "./Badge";
export { default as Button } from "./Button";
export { default as EmptyState } from "./EmptyState";
export { default as Panel } from "./Panel";
export { default as ThemeToggle } from "./ThemeToggle";
```

- [ ] **Step 8: 테스트 통과 확인**

```bash
cd apps/web && yarn test
```

기대: 프리미티브 테스트 9개 포함 전부 통과. 가드 테스트도 계속 통과해야 한다(새 파일이 `src/components/ui` 스캔 범위 안이다).

- [ ] **Step 9: 커밋**

```bash
git add apps/web/src/components/ui
git commit -m "feat(web): 공용 프리미티브 Panel/Button/Badge/EmptyState 추가"
```

---

### Task 6: 프리미티브 B — Field, Table, Modal

**Files:**
- Create: `apps/web/src/components/ui/Field.tsx`, `Field.module.css`
- Create: `apps/web/src/components/ui/Table.tsx`, `Table.module.css`
- Create: `apps/web/src/components/ui/Modal.tsx`, `Modal.module.css`
- Modify: `apps/web/src/components/ui/index.ts`
- Create: `apps/web/src/components/ui/__tests__/Modal.test.tsx`
- Modify: `apps/web/src/components/ui/__tests__/primitives.test.tsx`

**Interfaces:**
- Consumes: Task 5의 배럴
- Produces:
  ```ts
  Field: { label: string; htmlFor: string; error?: string; hint?: string;
           required?: boolean; children: ReactNode }
  Table: { dense?: boolean; stickyHeader?: boolean; className?: string; children: ReactNode }
  Modal: { open: boolean; onClose: () => void; title: string;
           footer?: ReactNode; size?: "sm" | "md" | "lg"; children: ReactNode }
  ```

**`Modal` 설계 결정:** 네이티브 `<dialog>` + `showModal()`을 쓴다. 포커스 트랩, Escape 닫기, top-layer 스태킹, `::backdrop`을 브라우저가 준다. 현재 코드베이스의 자체 구현 4곳(`ChatbotPopup`, `Diagnosis`, `MedicalCertificate`, `SearchPatientModal`)은 Escape도 포커스 트랩도 없다.

**jsdom 주의:** jsdom은 `HTMLDialogElement.showModal`을 구현하지 않는다. `Modal.test.tsx`에서 `showModal`/`close`를 스텁으로 채워야 한다. 아래 테스트 코드에 포함되어 있다.

- [ ] **Step 1: `Field`·`Table` 테스트 추가**

`primitives.test.tsx` 끝에 추가한다:

```tsx
import { Field, Table } from "../index";

describe("Field", () => {
  it("라벨을 입력에 연결한다", () => {
    render(
      <Field label="환자명" htmlFor="patient-name">
        <input id="patient-name" />
      </Field>
    );
    expect(screen.getByLabelText("환자명")).toBeInTheDocument();
  });

  it("error 를 alert 로 노출하고 aria-describedby 로 연결한다", () => {
    render(
      <Field label="환자명" htmlFor="patient-name" error="필수 항목입니다">
        <input id="patient-name" />
      </Field>
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("필수 항목입니다");
    expect(screen.getByLabelText("환자명")).toHaveAttribute("aria-describedby", alert.id);
  });

  it("required 면 입력에 required 를 전달한다", () => {
    render(
      <Field label="환자명" htmlFor="patient-name" required>
        <input id="patient-name" />
      </Field>
    );
    expect(screen.getByLabelText("환자명")).toBeRequired();
  });
});

describe("Table", () => {
  it("table 시맨틱을 유지한다", () => {
    render(
      <Table>
        <thead>
          <tr>
            <th scope="col">이름</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>김환자</td>
          </tr>
        </tbody>
      </Table>
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "이름" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "김환자" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: `Modal` 테스트 작성**

`apps/web/src/components/ui/__tests__/Modal.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import Modal from "../Modal";

// jsdom 은 <dialog> 의 모달 동작을 구현하지 않는다. open 속성만 흉내 낸다.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

describe("Modal", () => {
  it("open=false 면 내용을 표시하지 않는다", () => {
    render(
      <Modal open={false} onClose={() => {}} title="환자 검색">
        본문
      </Modal>
    );
    expect(screen.queryByText("본문")).toBeNull();
  });

  it("open=true 면 dialog 로 렌더하고 title 로 라벨링한다", () => {
    render(
      <Modal open onClose={() => {}} title="환자 검색">
        본문
      </Modal>
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAccessibleName("환자 검색");
    expect(screen.getByText("본문")).toBeInTheDocument();
  });

  it("cancel 이벤트(Escape)에서 onClose 를 호출한다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("닫기 버튼에서 onClose 를 호출한다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```bash
cd apps/web && yarn test src/components/ui
```

기대: `Field`/`Table`/`Modal` 미구현으로 실패.

- [ ] **Step 4: `Field` 구현**

`apps/web/src/components/ui/Field.tsx`:

```tsx
import { cloneElement, isValidElement } from "react";

import styles from "./Field.module.css";

interface FieldProps {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}

export default function Field({ label, htmlFor, error, hint, required, children }: FieldProps) {
  const errorId = `${htmlFor}-error`;
  const hintId = `${htmlFor}-hint`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ");

  // 입력 요소에 aria-describedby / required 를 주입한다.
  // 호출부가 이미 지정했으면 덮어쓰지 않는다.
  const control = isValidElement<Record<string, unknown>>(children)
    ? cloneElement(children, {
        "aria-describedby": children.props["aria-describedby"] ?? (describedBy || undefined),
        required: children.props.required ?? required,
      })
    : children;

  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={htmlFor}>
        {label}
        {required && (
          <span className={styles.required} aria-hidden="true">
            *
          </span>
        )}
      </label>
      {control}
      {hint && (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className={styles.error} id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
```

`apps/web/src/components/ui/Field.module.css`:

```css
.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.label {
  color: var(--text-muted);
  font-size: var(--font-size-sm);
  line-height: var(--line-height-sm);
}

.required {
  margin-left: 2px;
  color: var(--danger-text);
}

.hint {
  margin: 0;
  color: var(--text-muted);
  font-size: var(--font-size-xs);
}

.error {
  margin: 0;
  color: var(--danger-text);
  font-size: var(--font-size-xs);
}
```

- [ ] **Step 5: `Table` 구현**

`apps/web/src/components/ui/Table.tsx`:

```tsx
import styles from "./Table.module.css";

interface TableProps {
  dense?: boolean;
  stickyHeader?: boolean;
  className?: string;
  children: React.ReactNode;
}

export default function Table({ dense, stickyHeader, className, children }: TableProps) {
  return (
    <div className={styles.scroll}>
      <table
        className={[
          styles.table,
          dense ? styles.dense : null,
          stickyHeader ? styles.sticky : null,
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {children}
      </table>
    </div>
  );
}
```

`apps/web/src/components/ui/Table.module.css`:

```css
.scroll {
  width: 100%;
  overflow-x: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-base);
}

.table th {
  padding: 0 var(--space-3);
  height: var(--row-height);
  background: var(--surface-sunken);
  color: var(--text-muted);
  font-size: var(--font-size-xs);
  font-weight: 500;
  text-align: left;
  white-space: nowrap;
}

.table td {
  padding: 0 var(--space-3);
  height: var(--row-height);
  border-top: 1px solid var(--border);
  color: var(--text-primary);
}

.table tbody tr:hover {
  background: var(--accent-bg);
}

.table tbody tr[aria-selected="true"] {
  background: var(--accent-bg);
  box-shadow: inset 2px 0 0 var(--accent-fill);
}

.dense th,
.dense td {
  height: var(--control-height-sm);
}

.sticky thead th {
  position: sticky;
  top: 0;
  z-index: 1;
}
```

- [ ] **Step 6: `Modal` 구현**

`apps/web/src/components/ui/Modal.tsx`:

```tsx
"use client";

import { useEffect, useRef } from "react";

import Button from "./Button";
import styles from "./Modal.module.css";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
}

export default function Modal({ open, onClose, title, footer, size = "md", children }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // showModal 이 포커스 트랩·Escape·top-layer 를 담당한다.
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const handleCancel = (event: Event) => {
      event.preventDefault();
      onClose();
    };
    dialog.addEventListener("cancel", handleCancel);
    return () => dialog.removeEventListener("cancel", handleCancel);
  }, [onClose]);

  return (
    <dialog ref={ref} className={`${styles.dialog} ${styles[size]}`} aria-label={title}>
      {open && (
        <>
          <div className={styles.header}>
            <h2 className={styles.title}>{title}</h2>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="닫기">
              ✕
            </Button>
          </div>
          <div className={styles.body}>{children}</div>
          {footer && <div className={styles.footer}>{footer}</div>}
        </>
      )}
    </dialog>
  );
}
```

`apps/web/src/components/ui/Modal.module.css`:

```css
.dialog {
  padding: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-overlay);
  color: var(--text-primary);
  box-shadow: var(--shadow-lg);
  max-height: 85vh;
  overflow: hidden;
}

.dialog::backdrop {
  background: var(--backdrop);
}

.sm {
  width: min(420px, 92vw);
}

.md {
  width: min(640px, 92vw);
}

.lg {
  width: min(900px, 92vw);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
}

.title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: 600;
}

.body {
  padding: var(--space-4);
  max-height: 60vh;
  overflow: auto;
}

.footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border);
}
```

**주의:** `::backdrop`은 `<dialog>` 요소 자체의 상속을 받지 않아 `--backdrop`이 `:root`에서 해석된다. `tokens.css`가 `:root`에 정의하므로 문제없다.

- [ ] **Step 7: 배럴 갱신**

`apps/web/src/components/ui/index.ts`에 추가한다:

```ts
export { default as Field } from "./Field";
export { default as Modal } from "./Modal";
export { default as Table } from "./Table";
```

- [ ] **Step 8: 테스트 통과 확인**

```bash
cd apps/web && yarn test && yarn build
```

기대: 전부 통과.

- [ ] **Step 9: 커밋**

```bash
git add apps/web/src/components/ui
git commit -m "feat(web): Field/Table/Modal 프리미티브 추가, 모달을 네이티브 dialog 로 전환"
```

---

### Task 7: 스타일가이드 화면

**Files:**
- Create: `apps/web/src/app/styleguide/page.tsx`
- Create: `apps/web/src/app/styleguide/page.module.css`

**Interfaces:**
- Consumes: `src/components/ui`의 프리미티브 전체
- Produces: `/styleguide` 경로. Task 8~12의 시각 기준 화면이며 관리자 콘솔 Task 5·6의 구현 레퍼런스.

**요구사항:**
- 프리미티브 8종을 **모든 variant / tone / size 조합**으로 렌더한다.
  - `Button` — variant 4 × size 2 × (기본 / `loading` / `disabled`)
  - `Badge` — tone 5
  - `Panel` — title 있음 / 없음 / actions 있음 / `padding="none"` + `Table`
  - `Field` — 기본 / `hint` / `error` / `required`
  - `Table` — 기본 / `dense` / `stickyHeader` / 선택 행(`aria-selected`)
  - `Modal` — 열기 버튼으로 sm/md/lg 각각 확인
  - `EmptyState` — description 있음 / action 있음
  - `ThemeToggle` — 페이지 상단
- 임상 상태 배지 4종(대기·진료중·완료·취소)을 spec §4.2 매핑대로 보여준다.
- 의미 토큰 전체를 색상 견본으로 나열한다. 각 견본은 토큰 이름을 함께 표시한다.
- 페이지는 `"use client"`다(`Modal`·`ThemeToggle`이 클라이언트 컴포넌트).

- [ ] **Step 1: 프로덕션 노출 차단 확인**

페이지 최상단에서 프로덕션 빌드일 때 404를 낸다:

```tsx
"use client";

import { notFound } from "next/navigation";

// ...컴포넌트 안 첫 줄
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
```

- [ ] **Step 2: 페이지 구현**

`page.module.css`는 섹션 레이아웃만 담당한다 — 견본 그리드, 섹션 간격, 토큰 스와치 타일. 색상은 전부 토큰이다.

토큰 스와치는 `style={{ background: "var(--surface-raised)" }}`처럼 **토큰 참조**로 쓴다. GC-2가 금지하는 것은 색상 **리터럴**이고 `var()` 참조는 리터럴이 아니다.

아래 골격을 따르고 나머지 섹션을 같은 패턴으로 채운다:

```tsx
"use client";

import { useState } from "react";
import { notFound } from "next/navigation";

import { Badge, Button, EmptyState, Field, Modal, Panel, Table, ThemeToggle } from "@/components/ui";
import styles from "./page.module.css";

const SURFACE_TOKENS = [
  "surface-canvas",
  "surface-sunken",
  "surface-raised",
  "surface-overlay",
  "surface-chrome",
  "surface-chrome-hover",
  "surface-chrome-active",
];

const TEXT_TOKENS = ["text-primary", "text-secondary", "text-muted", "text-on-chrome"];

const ROLE_PAIRS = [
  ["accent-bg", "accent-text"],
  ["success-bg", "success-text"],
  ["warning-bg", "warning-text"],
  ["danger-bg", "danger-text"],
];

const CLINIC_STATES = [
  { label: "대기", tone: "accent" as const },
  { label: "진료중", tone: "warning" as const },
  { label: "완료", tone: "success" as const },
  { label: "취소", tone: "danger" as const },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      <div className={styles.row}>{children}</div>
    </section>
  );
}

export default function StyleguidePage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  const [openSize, setOpenSize] = useState<"sm" | "md" | "lg" | null>(null);

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <h1>디자인 시스템</h1>
        <ThemeToggle />
      </header>

      <Section title="Button">
        {(["primary", "secondary", "ghost", "danger"] as const).map((variant) =>
          (["md", "sm"] as const).map((size) => (
            <div key={`${variant}-${size}`} className={styles.cell}>
              <Button variant={variant} size={size}>
                {variant}/{size}
              </Button>
              <Button variant={variant} size={size} loading>
                loading
              </Button>
              <Button variant={variant} size={size} disabled>
                disabled
              </Button>
            </div>
          ))
        )}
      </Section>

      <Section title="Badge">
        {(["neutral", "accent", "success", "warning", "danger"] as const).map((tone) => (
          <Badge key={tone} tone={tone}>
            {tone}
          </Badge>
        ))}
      </Section>

      <Section title="임상 상태">
        {CLINIC_STATES.map((state) => (
          <Badge key={state.label} tone={state.tone}>
            {state.label}
          </Badge>
        ))}
      </Section>

      <Section title="Modal">
        {(["sm", "md", "lg"] as const).map((size) => (
          <Button key={size} onClick={() => setOpenSize(size)}>
            {size} 열기
          </Button>
        ))}
        <Modal
          open={openSize !== null}
          onClose={() => setOpenSize(null)}
          title={`모달 ${openSize ?? ""}`}
          size={openSize ?? "md"}
          footer={<Button variant="primary" onClick={() => setOpenSize(null)}>확인</Button>}
        >
          Escape 로 닫히고 포커스가 열기 버튼으로 돌아가는지 확인한다.
        </Modal>
      </Section>

      <Section title="표면 토큰">
        {SURFACE_TOKENS.map((token) => (
          <div key={token} className={styles.swatch} style={{ background: `var(--${token})` }}>
            <span className={styles.swatchLabel}>--{token}</span>
          </div>
        ))}
      </Section>

      {/* Panel, Field, Table, EmptyState, TEXT_TOKENS, ROLE_PAIRS 섹션도 같은 패턴으로 추가한다. */}
    </div>
  );
}
```

`.swatchLabel`은 `--text-on-chrome`처럼 어느 배경에서도 읽히는 색이 아니므로, 라벨을 스와치 **바깥**에 두거나 스와치 아래에 `--text-muted`로 적는다. 스와치 안에 겹쳐 놓으면 밝은 표면 위에서 라벨이 사라진다.

- [ ] **Step 3: 두 테마에서 확인**

```bash
cd apps/web && yarn dev
```

`http://localhost:3000/styleguide`에서 토글로 라이트/다크를 전환하며 확인한다.

체크: 모든 텍스트가 두 테마에서 읽히는가. 경계선이 두 테마에서 보이는가. `Modal`이 Escape로 닫히고 포커스가 열기 버튼으로 돌아오는가.

- [ ] **Step 4: 테스트·빌드 확인**

```bash
cd apps/web && yarn test && yarn build
```

- [ ] **Step 5: 커밋**

```bash
git add apps/web/src/app/styleguide
git commit -m "feat(web): 개발 전용 스타일가이드 화면 추가"
```

---

### Task 8: 앱 셸 재스킨

**Files:**
- Modify: `apps/web/src/components/Header.tsx`, `Header.module.css`
- Modify: `apps/web/src/components/Sidebar.module.css`
- Modify: `apps/web/src/app/(dashboard)/dashboard/page.module.css`
- Modify: `apps/web/src/app/(auth)/admin/layout.tsx`, `layout.module.css`
- Modify: `apps/web/src/styles/__tests__/no-hardcoded-color.test.ts` (SCAN_DIRS 확대)
- Create: `apps/web/src/components/__tests__/Header.test.tsx`

**Interfaces:**
- Consumes: `Button`, `ThemeToggle`, 토큰 전체
- Consumes: `getMe()` — `src/services/auth`. 반환 객체에 `id`와 사용자명 필드가 있다. **실제 필드명을 코드에서 확인하고 쓸 것**(`src/types/api.ts` 또는 `services/auth.ts`). `Header.tsx`는 반드시 `@/services/auth` 경로로 import 해야 한다 — 테스트의 `vi.mock("@/services/auth")`가 같은 지정자를 가로채기 때문이다. 상대 경로로 import 하면 mock이 적용되지 않는다.

**이 태스크가 처리하는 spec §9.1의 두 항목:**

1. `Header.tsx`에 `<span className={styles.username}>김동국</span>`이 하드코딩되어 있다. 누가 로그인하든 같은 이름이 뜬다. `getMe()`로 교체한다. 조회 실패 시 이름 자리를 비우고 화면은 정상 동작해야 한다.
2. 관리자 콘솔에는 헤더가 없어 대시보드 복귀 경로도 로그아웃도 없다. `admin/layout.tsx`가 같은 `Header`를 렌더하고 자체 사이드바는 유지한다.

**색상 매핑 (GC-7 적용):**

| 위치 | 기존 | 토큰 |
|---|---|---|
| `Header.module.css` `.header` | `#2563eb` | `--surface-chrome` + `--text-on-chrome` |
| `.button`, `.chatbotBtn` | `rgba(255,255,255,0.15~0.4)` | `Button variant="ghost"` |
| `Sidebar.module.css` `.sidebar` | `#333336` | `--surface-chrome` |
| `.menuItem:hover` | `#303032` | `--surface-chrome-hover` |
| `.menuItem.active` | `#515154` | `--surface-chrome-active` + 좌측 2px `--accent-fill` |
| `.sidebar` border-right | `#e2e8f0` | `--border` |
| `dashboard/page.module.css` `.contentArea` | `#5E5E61` | `--surface-canvas` |
| `admin/layout.module.css` `.sidebar` | `#fafafa` | `--surface-raised` |
| `.navLinkActive` | `#1a4f8a` | `--accent-bg` + `--accent-text` |
| `.navLink` | `#333` / hover `#eee` | `--text-secondary` / `--accent-bg` |
| `.gate` | `#666` | `--text-muted` |

**추가 요구:** `Header`의 제목을 `슈붕보다팥붕`에서 `BitComputer EMR`로 바꾼다.

- [ ] **Step 1: 실패하는 테스트 작성**

`apps/web/src/components/__tests__/Header.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/auth", () => ({
  getMe: vi.fn(),
}));

import { getMe } from "@/services/auth";
import ThemeProvider from "@/components/theme/ThemeProvider";
import Header from "../Header";

function renderHeader() {
  return render(
    <ThemeProvider>
      <Header />
    </ThemeProvider>
  );
}

describe("Header", () => {
  beforeEach(() => {
    vi.mocked(getMe).mockReset();
  });

  it("서비스명을 BitComputer EMR 로 표시한다", () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, name: "김의사" } as never);
    renderHeader();
    expect(screen.getByRole("heading", { name: "BitComputer EMR" })).toBeInTheDocument();
  });

  it("로그인한 사용자 이름을 표시한다", async () => {
    vi.mocked(getMe).mockResolvedValue({ id: 7, name: "이간호" } as never);
    renderHeader();
    await waitFor(() => expect(screen.getByText("이간호")).toBeInTheDocument());
  });

  it("사용자 조회에 실패해도 헤더가 렌더된다", async () => {
    vi.mocked(getMe).mockRejectedValue(new Error("401"));
    renderHeader();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "BitComputer EMR" })).toBeInTheDocument()
    );
    expect(screen.queryByText("김동국")).toBeNull();
  });

  it("테마 토글을 포함한다", () => {
    vi.mocked(getMe).mockResolvedValue({ id: 1, name: "김의사" } as never);
    renderHeader();
    expect(screen.getByRole("button", { name: /테마/ })).toBeInTheDocument();
  });
});
```

**주의:** `getMe()`의 실제 반환 타입을 확인하고 mock 객체의 필드명을 맞춘다. 위 `name` 필드는 가정이다 — 실제 필드명이 다르면 테스트와 구현을 함께 맞춘다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/web && yarn test src/components/__tests__/Header.test.tsx
```

기대: `슈붕보다팥붕`이 렌더되어 헤딩 이름 불일치로 실패.

- [ ] **Step 3: `Header.tsx` 재작성**

`"use client"` 유지. `useEffect`로 `getMe()`를 호출해 사용자명을 상태에 담고, 실패는 `catch`로 삼켜 이름을 비운다. `<h1>`은 `BitComputer EMR`. 오른쪽 영역에 `ThemeToggle`, 사용자명, 로그아웃 `Link`를 둔다. 로그아웃 링크는 `Button` 스타일이 아니라 `Link`를 유지한다(GC-1 — 기존 시맨틱 보존).

`activeMenu` prop은 현재 `void activeMenu`로 버려지고 있다. 이 태스크는 그것을 그대로 둔다(범위 밖).

- [ ] **Step 4: 셸 CSS 4개 재작성**

위 매핑표대로 `Header.module.css`, `Sidebar.module.css`, `dashboard/page.module.css`, `admin/layout.module.css`를 토큰 기반으로 재작성한다. GC-4에 따라 `grid-template-columns`, breakpoint, 폭 값은 유지한다. GC-5에 따라 패딩·간격을 토큰 스케일로 올린다.

- [ ] **Step 5: 관리자 레이아웃에 헤더 추가**

`admin/layout.tsx`의 `styles.shell`을 세로 flex로 감싸 `<Header />`를 위에 두고 그 아래에 기존 사이드바+콘텐츠 그리드를 둔다. 역할 게이트(`allowed === null` / `!allowed`) 분기는 그대로 유지한다.

- [ ] **Step 6: 가드 스캔 범위 확대**

`no-hardcoded-color.test.ts`의 `SCAN_DIRS`에 추가한다:

```ts
const SCAN_DIRS = [
  "src/styles",
  "src/components/ui",
  "src/components/theme",
  "src/app/(dashboard)",
  "src/app/(auth)/admin",
];
```

`Header.module.css`와 `Sidebar.module.css`는 `src/components` 바로 아래라 아직 범위 밖이다. Task 12에서 `["src"]`로 확대할 때 포함된다. **다만 이 태스크에서도 두 파일에 리터럴을 남기지 않는다** — 아래 Step 7이 확인한다.

- [ ] **Step 7: 리터럴 잔존 확인**

```bash
cd apps/web && grep -n "#[0-9a-fA-F]\{3,8\}\|rgba\?(" \
  src/components/Header.module.css \
  src/components/Sidebar.module.css \
  "src/app/(dashboard)/dashboard/page.module.css" \
  "src/app/(auth)/admin/layout.module.css" \
  && echo "리터럴 잔존 — 수정 필요" || echo "리터럴 없음"
```

기대: "리터럴 없음".

- [ ] **Step 8: 테스트·빌드 확인**

```bash
cd apps/web && yarn test && yarn build
```

- [ ] **Step 9: 커밋**

```bash
git add apps/web/src
git commit -m "feat(web): 앱 셸 재스킨, 서비스명 변경, 관리자 콘솔에 헤더 통일"
```

---

### Task 9: 인증 화면 재스킨

**Files:**
- Modify: `apps/web/src/app/(auth)/login/page.tsx`
- Modify: `apps/web/src/app/(auth)/signup/page.tsx`
- Create: `apps/web/src/app/(auth)/login/page.module.css`
- Create: `apps/web/src/app/(auth)/signup/page.module.css`
- Modify: `apps/web/src/components/common/AuthLink.tsx`
- Modify: `apps/web/src/styles/__tests__/no-hardcoded-color.test.ts` (SCAN_DIRS 확대)

**Interfaces:**
- Consumes: `Panel`, `Field`, `Button`

**배경:** 두 화면 모두 CSS module 없이 인라인 `style={{}}`만 쓴다. 로그인 화면의 `#ddd`, `#c00`, `#111`이 GC-2 위반이며 다크 모드에서 전부 깨진다.

**요구사항:**
- 폼 전체를 `Panel`로 감싸고 각 입력을 `Field`로 감싼다.
- 제출 버튼은 `Button variant="primary"` — 화면당 유일한 primary(GC-5).
- 오류 표시는 현재 `role="alert"`를 쓰고 있다. `Field error`가 같은 역할을 하므로 이관하되 **`role="alert"`가 사라지지 않게 한다**(GC-1).
- 화면을 세로 중앙에 두되 `min-height: 100dvh`를 쓴다(`100vh`는 모바일 브라우저 주소창 때문에 잘린다).
- `signup/page.tsx`의 부서 입력은 이 태스크에서 건드리지 않는다. 관리자 콘솔 Task 5가 select로 전환한다.

- [ ] **Step 1: 두 화면 재작성**

인라인 `style` 속성을 전부 제거하고 `page.module.css`로 옮긴다. `login`과 `signup`이 같은 레이아웃을 쓰므로 두 CSS의 셸 규칙(중앙 정렬 컨테이너, 폼 그리드)은 동일해야 한다.

- [ ] **Step 2: `AuthLink` 확인**

`src/components/common/AuthLink.tsx`가 인라인 스타일을 쓴다. 색·간격 지정을 토큰 기반 클래스로 옮긴다.

- [ ] **Step 3: 가드 스캔 범위 확대**

`SCAN_DIRS`에 `"src/app/(auth)"`, `"src/components/common"`을 추가한다. `src/app/(auth)/admin`은 이미 들어 있으므로 `"src/app/(auth)"`가 이를 포함한다 — 중복 항목은 제거한다.

- [ ] **Step 4: 수동 확인**

```bash
cd apps/web && yarn dev
```

`/login`과 `/signup`을 두 테마에서 확인한다. 잘못된 자격 증명으로 로그인해 오류 메시지가 `--danger-text`로 읽히는지 본다.

- [ ] **Step 5: 테스트·빌드 확인**

```bash
cd apps/web && yarn test && yarn build
```

- [ ] **Step 6: 커밋**

```bash
git add apps/web/src
git commit -m "feat(web): 로그인·회원가입 화면을 프리미티브 기반으로 재구성"
```

---

### Task 10: 환자접수 화면 재스킨

**Files (전부 Modify):**
- `apps/web/src/components/PatientForm.{tsx,module.css}`
- `apps/web/src/components/MedicalInfo.{tsx,module.css}`
- `apps/web/src/components/WaitingStatus.{tsx,module.css}`
- `apps/web/src/components/SpecialNote.{tsx,module.css}`
- `apps/web/src/components/History.tsx`, `HistoryDiagnose.module.css`
- `apps/web/src/components/ActionBar.{tsx,module.css}`
- `apps/web/src/components/PatientInfoBar.{tsx,module.css}`
- `apps/web/src/components/SearchPatientModal.{tsx,module.css}`
- `apps/web/src/styles/__tests__/no-hardcoded-color.test.ts` (SCAN_DIRS 확대)

**Interfaces:**
- Consumes: `Panel`, `Button`, `Field`, `Table`, `Badge`, `EmptyState`, `Modal`

**요구사항:**

1. **패널 셸 이관.** 각 컴포넌트가 자체 `.header`/`.title`을 갖고 있다. `Panel`로 교체한다. `title`은 기존 제목 텍스트를 그대로 쓴다(GC-1).
2. **목록을 `Table`로.** `WaitingStatus`(62개 리터럴)의 목록이 `<div>` 격자면 `<table>`로 승격한다. 이는 시맨틱 **개선**이라 GC-1이 허용한다. 선택된 행에 `aria-selected="true"`를 준다.
3. **상태 표시를 `Badge`로.** 대기/진료중/완료를 spec §4.2 매핑대로 tone에 연결한다.
4. **`SearchPatientModal`을 `Modal`로.** 자체 `position: fixed` 오버레이(46개 리터럴)를 제거한다. 열림 상태를 부모가 제어하도록 `open`/`onClose` prop을 받게 바꾼다. 기존 호출부의 열기/닫기 경로를 따라가 맞춘다.
5. **빈 상태.** 목록이 비었을 때 `EmptyState`를 렌더한다.
6. **`WaitingStatus.tsx`의 인라인 스타일** 제거.

**색상 매핑:** GC-7 표를 따른다.

- [ ] **Step 1: 컴포넌트별 재작성**

한 번에 한 컴포넌트씩 처리하고, 각 컴포넌트마다 아래를 확인한다:
- 기존 제목 텍스트가 보존되었는가
- 기존 `role`/`aria-*` 속성이 보존되었는가
- 리터럴이 0인가

- [ ] **Step 2: 모달 호출부 확인**

```bash
cd apps/web && grep -rn "SearchPatientModal" src
```

모든 호출부가 새 `open`/`onClose` 계약에 맞는지 확인한다.

- [ ] **Step 3: 가드 스캔 범위 확대**

`SCAN_DIRS`에 위에서 처리한 컴포넌트가 포함되도록 한다. `src/components`를 통째로 넣으면 아직 처리하지 않은 진료실 컴포넌트가 걸린다. 이 태스크에서는 **파일 단위 허용 목록 대신 스캔 범위를 유지**하고, Step 4의 grep으로 확인한다. `SCAN_DIRS` 확대는 Task 12에서 한 번에 한다.

- [ ] **Step 4: 리터럴 잔존 확인**

```bash
cd apps/web && grep -ln "#[0-9a-fA-F]\{3,8\}\|rgba\?(" \
  src/components/PatientForm.module.css src/components/MedicalInfo.module.css \
  src/components/WaitingStatus.module.css src/components/SpecialNote.module.css \
  src/components/HistoryDiagnose.module.css src/components/ActionBar.module.css \
  src/components/PatientInfoBar.module.css src/components/SearchPatientModal.module.css \
  src/components/WaitingStatus.tsx \
  && echo "리터럴 잔존 — 수정 필요" || echo "리터럴 없음"
```

- [ ] **Step 5: 수동 확인**

```bash
cd apps/web && yarn dev
```

`/dashboard`의 환자접수 탭을 두 테마에서 확인한다. 환자 검색 모달을 열고 Escape로 닫히는지, 포커스가 열기 버튼으로 돌아오는지 본다.

- [ ] **Step 6: 테스트·빌드 확인**

```bash
cd apps/web && yarn test && yarn build
```

- [ ] **Step 7: 커밋**

```bash
git add apps/web/src
git commit -m "feat(web): 환자접수 화면 재스킨, 환자 검색 모달을 dialog 기반으로 전환"
```

---

### Task 11: 진료실 화면 재스킨

**Files (전부 Modify):**
- `apps/web/src/components/Disease.{tsx,module.css}`
- `apps/web/src/components/Diagnosis.{tsx,module.css}`
- `apps/web/src/components/Calender.{tsx,module.css}`
- `apps/web/src/components/TimeLine.{tsx,module.css}`
- `apps/web/src/components/ViewDataBase.{tsx,module.css}`
- `apps/web/src/components/AIReport.{tsx,module.css}`
- `apps/web/src/components/ChatbotPopup.{tsx,module.css}`

**Interfaces:**
- Consumes: 프리미티브 전체

**요구사항:**

1. `Diagnosis.module.css`가 80개로 리터럴이 가장 많다. `position: fixed` 오버레이를 포함하므로 `Modal`로 이관한다.
2. `ChatbotPopup`도 `position: fixed` 오버레이다. **다만 팝업이 모달이 아니라 비모달 패널이라면 `<dialog>`의 `show()`(모달 아님)를 쓰거나 `Panel` + 절대 위치로 둔다.** 현재 동작을 먼저 확인하고 결정한다 — 배경 클릭이 막혀야 하면 `Modal`, 아니면 비모달.
3. **`AIReport.tsx`는 특별 취급한다.** 유일한 기존 프론트 테스트가 이 컴포넌트를 검증한다. 다음을 반드시 보존한다:
   - `<button>` 접근성 이름 `"AI 분석"`
   - `role="status"` 요소와 그 텍스트에 포함된 `"mock"`
   - 경고 텍스트가 렌더될 때 `role="status"`가 사라지는 현재 동작
   `engineStatus` 경고 배지는 `Badge tone="warning"`으로 바꾼다.
4. 보라색(`#7c3aed`, `#6d28d9`, `#a855f7`, `#a78bfa`)은 `--accent-*`로 통합한다. 보라 램프를 도입하지 않는다(GC-7).
5. 반투명 글로우(`rgba(59,130,246,0.3)` 등)는 제거하고 경계선 또는 `--accent-bg`로 대체한다.

- [ ] **Step 1: `ChatbotPopup` 동작 확인**

```bash
cd apps/web && grep -n "overlay\|onClick" src/components/ChatbotPopup.tsx | head -20
```

배경 클릭으로 닫히는지, 배경 상호작용이 막히는지 확인하고 모달/비모달을 결정한다. 결정과 근거를 태스크 보고서에 적는다.

- [ ] **Step 2: `AIReport` 테스트를 먼저 돌려 기준선 확보**

```bash
cd apps/web && yarn test src/components/__tests__/AIReport.test.tsx
```

기대: 통과. 이 상태를 재스킨 후에도 유지해야 한다.

- [ ] **Step 3: 컴포넌트별 재작성**

한 번에 한 컴포넌트씩. `AIReport`를 마지막에 처리하고 매번 그 테스트를 돌린다.

- [ ] **Step 4: 리터럴 잔존 확인**

```bash
cd apps/web && grep -ln "#[0-9a-fA-F]\{3,8\}\|rgba\?(" \
  src/components/Disease.module.css src/components/Diagnosis.module.css \
  src/components/Calender.module.css src/components/TimeLine.module.css \
  src/components/ViewDataBase.module.css src/components/AIReport.module.css \
  src/components/ChatbotPopup.module.css src/components/AIReport.tsx \
  && echo "리터럴 잔존 — 수정 필요" || echo "리터럴 없음"
```

- [ ] **Step 5: 수동 확인**

`/dashboard`의 진료실 탭을 두 테마에서 확인한다. 상병·처방 모달, 챗봇 팝업, AI 분석 버튼을 각각 눌러본다.

- [ ] **Step 6: 테스트·빌드 확인**

```bash
cd apps/web && yarn test && yarn build
```

기대: `AIReport.test.tsx` 포함 전부 통과.

- [ ] **Step 7: 커밋**

```bash
git add apps/web/src
git commit -m "feat(web): 진료실 화면 재스킨"
```

---

### Task 12: 진단서·기타 재스킨과 가드 전체 확대

**Files (전부 Modify):**
- `apps/web/src/components/MedicalCertificate.{tsx,module.css}`
- `apps/web/src/components/CertificateList.{tsx,module.css}`
- `apps/web/src/components/CertificateBottom.{tsx,module.css}`
- `apps/web/src/components/CertificatePatientSearch.{tsx,module.css}`
- `apps/web/src/app/evaluation/page.{tsx,module.css}`
- `apps/web/src/app/(auth)/admin/users/page.module.css`
- `apps/web/src/styles/__tests__/no-hardcoded-color.test.ts`

**Interfaces:**
- Produces: `SCAN_DIRS = ["src"]` — GC-2가 전 코드베이스에 적용된 상태

**요구사항:**

1. `MedicalCertificate`(68개 리터럴)는 `position: fixed` 오버레이를 포함한다. `Modal`로 이관한다.
2. **진단서 인쇄·PDF 출력 경로에 주의한다.** `html2canvas`와 `pdf-lib`를 쓰므로 CSS 변수가 캡처 시점에 해석되는지 확인해야 한다. `html2canvas`는 `getComputedStyle`을 쓰므로 CSS 변수가 이미 해석된 값으로 읽힌다 — 정상 동작이 기대되지만, **다크 모드에서 진단서를 PDF로 뽑으면 검은 배경이 그대로 찍힌다.** 진단서 출력 영역은 테마와 무관하게 항상 흰 배경·검은 글자여야 한다.
   해결: 인쇄 대상 컨테이너에만 `--surface-raised`/`--text-primary`를 라이트 값으로 재정의하는 클래스를 둔다. `tokens.css`에 인쇄용 스코프를 추가한다:
   ```css
   .print-surface {
     --surface-raised: var(--white);
     --surface-canvas: var(--white);
     --text-primary: var(--slate-900);
     --text-secondary: var(--slate-700);
     --border: var(--slate-300);
   }
   ```
   이 규칙은 `tokens.css`에 두므로 GC-2를 위반하지 않는다. 클래스명은 CSS module이 아니라 전역이어야 하므로 `globals.css`에 둔다 — **`tokens.css`가 아닌 `globals.css`에 두되 값은 전부 `var()` 참조라 리터럴이 없다.**
3. `evaluation/page.tsx`의 인라인 스타일을 제거한다.
4. `admin/users/page.module.css`(38개 리터럴)를 `Panel` + `Table` + `Button` 기반으로 재작성한다. 이 화면은 관리자 콘솔 Task 5·6의 형제 화면이므로 **여기서 확립한 패턴이 부서 관리·감사 로그 화면의 기준이 된다.**

- [ ] **Step 1: 인쇄 스코프 클래스 추가**

`globals.css`에 위 `.print-surface` 규칙을 추가하고, `MedicalCertificate`의 캡처 대상 컨테이너에 적용한다.

- [ ] **Step 2: 컴포넌트별 재작성**

- [ ] **Step 3: 진단서 PDF 출력 확인**

```bash
cd apps/web && yarn dev
```

다크 모드에서 `/dashboard` 진단서 탭에 들어가 PDF를 출력하고, 결과물이 흰 배경·검은 글자인지 확인한다. **이것이 이 태스크의 핵심 검증이다.**

- [ ] **Step 4: 가드 스캔 범위를 전체로 확대**

`no-hardcoded-color.test.ts`:

```ts
const SCAN_DIRS = ["src"];
```

- [ ] **Step 5: 가드 테스트 통과 확인**

```bash
cd apps/web && yarn test src/styles/__tests__/no-hardcoded-color.test.ts
```

기대: 통과. 실패하면 보고된 파일을 GC-7 매핑표에 따라 고친다. **테스트를 느슨하게 만들거나 `ALLOWED`에 파일을 추가하지 않는다.**

- [ ] **Step 6: 전체 테스트·빌드**

```bash
cd apps/web && yarn test && yarn build
```

- [ ] **Step 7: 컨테이너 기동 확인**

```bash
docker compose -f infra/docker-compose.yml up -d --build web
```

`http://localhost:3000`에서 두 테마를 확인한다.

- [ ] **Step 8: 커밋**

```bash
git add apps/web/src
git commit -m "feat(web): 진단서·평가·직원 관리 화면 재스킨, 색상 리터럴 가드 전면 적용"
```

---

## 완료 확인

전 태스크 종료 후 spec §11의 11개 항목을 확인한다.

```bash
cd apps/web && yarn test && yarn build
```

```bash
cd apps/web && grep -rn "#[0-9a-fA-F]\{3,8\}\|rgba\?(\|hsla\?(" src --include="*.css" --include="*.tsx" | grep -v "src/styles/tokens.css" | grep -v "__tests__"
```

기대: 출력 없음.

수동 확인 항목:
- 테마 토글 3상태 순환, 새로고침 후 유지
- 브라우저 JS 비활성 상태에서 OS 다크 설정 반영
- 첫 페인트에 라이트 화면이 번쩍이지 않음
- 모달 4곳이 Escape로 닫히고 포커스가 복귀
- Header가 `BitComputer EMR`과 실제 로그인 사용자를 표시
- 관리자 콘솔에 헤더가 보이고 대시보드로 돌아갈 수 있음
- 다크 모드에서 뽑은 진단서 PDF가 흰 배경
