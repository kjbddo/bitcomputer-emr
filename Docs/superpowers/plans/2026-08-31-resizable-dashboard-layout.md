# 대시보드 레이아웃 사용자 조절 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드 세 탭의 열 너비와 패널 높이를 경계 드래그로 조절하고, 그 배치를 브라우저에 탭별로 저장한다.

**Architecture:** 하드코딩된 그리드 치수를 CSS 변수로 빼고 폴백값을 현재 값으로 둔다(변수가 없으면 지금과 동일 동작). 순수 함수 저장 계층 → React 훅 → 핸들 컴포넌트 → 페이지 배선 순으로 아래에서 위로 쌓는다. 외부 라이브러리는 쓰지 않는다.

**Tech Stack:** Next.js(App Router), React 19, TypeScript, CSS Modules, vitest + @testing-library/react

**Spec:** `Docs/superpowers/specs/2026-08-31-resizable-dashboard-layout-design.md`

## Global Constraints

- 대상은 `apps/web/src/app/(dashboard)/dashboard/` 한 페이지다. 다른 화면의 `grid-template-columns` 는 건드리지 않는다.
- 외부 라이브러리를 추가하지 않는다. `pointerdown` / `setPointerCapture` / `pointermove` / `pointerup` 으로 구현한다.
- 각 축(열, 각 열의 행)에 `null`(= `1fr`) 트랙이 **최소 하나** 남아야 한다. 이 불변식이 깨지면 창 크기 변경 시 레이아웃이 무너진다.
- 최소 크기: 열 `200`px, 행 `120`px. 상수로 두고 하드코딩하지 않는다.
- 저장값이 손상됐거나 길이가 안 맞거나 `localStorage` 가 예외를 던지면 **조용히 기본값으로** 떨어진다. 화면이 죽지 않는다.
- 뷰포트 `1024px` 이하에서는 CSS 변수를 **아예 붙이지 않는다**(저장값은 지우지 않는다). 인라인 변수가 미디어쿼리를 이기기 때문이다.
- 핸들은 `role="separator"`, `tabIndex={0}`, 화살표 키 `10`px 이동을 지원한다.
- 새 색을 만들지 않는다. 기존 토큰(`--border`, `--border-strong`, `--space-*`)만 쓴다.
- 커밋 메시지 본문은 한국어. 메타데이터 푸터·이모지 금지.
- Windows 에서 `python3` 은 Microsoft Store 스텁이라 쓰지 않는다(이 계획에는 파이썬이 필요 없다).

---

## File Structure

| 파일 | 책임 |
|---|---|
| `apps/web/src/utils/layoutStorage.ts` | 저장 키, 직렬화, 유효성 검사, 기본값, 클램프. **순수 함수, DOM 의존 없음** |
| `apps/web/src/utils/__tests__/layoutStorage.test.ts` | 위 단위 테스트 |
| `apps/web/src/hooks/useResizableLayout.ts` | 치수 상태, 복원·저장, 델타 적용, 뷰포트 가드 |
| `apps/web/src/hooks/__tests__/useResizableLayout.test.tsx` | 훅 테스트 |
| `apps/web/src/components/ResizeHandle.tsx` | 경계 하나. pointer·키보드 입력을 델타 콜백으로 |
| `apps/web/src/components/ResizeHandle.module.css` | 핸들 스타일 |
| `apps/web/src/components/__tests__/ResizeHandle.test.tsx` | 핸들 테스트 |
| `apps/web/src/app/(dashboard)/dashboard/page.module.css` | 치수를 CSS 변수로, 열을 flex→grid |
| `apps/web/src/app/(dashboard)/dashboard/page.tsx` | 훅 배선, 핸들 삽입, "기본 배치로" 버튼 |

`hooks/` 디렉터리는 아직 없다. Task 2 에서 만든다.

---

## Task 1: 저장 계층 (순수 함수)

**Files:**
- Create: `apps/web/src/utils/layoutStorage.ts`
- Test: `apps/web/src/utils/__tests__/layoutStorage.test.ts`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `type TabId = "환자접수" | "진료실" | "진단서"`
  - `type Track = number | null`
  - `type LayoutState = { columns: Track[]; rows: Record<string, Track[]> }`
  - `MIN_COLUMN_PX = 200`, `MIN_ROW_PX = 120`
  - `DEFAULT_LAYOUTS: Record<TabId, LayoutState>`
  - `storageKey(tab: TabId): string`
  - `loadLayout(tab: TabId): LayoutState`
  - `saveLayout(tab: TabId, state: LayoutState): void`
  - `clearLayout(tab: TabId): void`
  - `HANDLE_TRACK_PX = 6`
  - `toTrackList(tracks: Track[], min: number): string`
  - `applyDelta(tracks: Track[], index: number, deltaPx: number, min: number, containerPx: number): Track[]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`apps/web/src/utils/__tests__/layoutStorage.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_LAYOUTS,
  MIN_COLUMN_PX,
  MIN_ROW_PX,
  applyDelta,
  clearLayout,
  loadLayout,
  saveLayout,
  storageKey,
  toTrackList,
} from "../layoutStorage";

beforeEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("저장 키", () => {
  it("탭마다 다른 키를 쓴다", () => {
    expect(storageKey("환자접수")).not.toBe(storageKey("진료실"));
    expect(storageKey("환자접수")).toContain("v1");
  });
});

describe("왕복", () => {
  it("저장한 값을 그대로 돌려준다", () => {
    const state = { columns: [320, null, 400], rows: { left: [200, null] } };
    saveLayout("진료실", state);
    expect(loadLayout("진료실")).toEqual(state);
  });

  it("clearLayout 은 그 탭만 지운다", () => {
    saveLayout("진료실", { columns: [320, null, 400], rows: {} });
    saveLayout("진단서", { columns: [300, null, null], rows: {} });
    clearLayout("진료실");
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
    expect(loadLayout("진단서").columns).toEqual([300, null, null]);
  });
});

describe("손상값은 기본값으로 떨어진다", () => {
  it("JSON 이 아니면", () => {
    window.localStorage.setItem(storageKey("진료실"), "{{{");
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("열 개수가 안 맞으면", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [300, null], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("숫자도 null 도 아닌 값이 섞이면", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [300, "wide", 400], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("최소값보다 작은 값이 있으면", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [10, null, 400], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("1fr 트랙이 하나도 없으면 — 창 크기 변경 시 레이아웃이 무너진다", () => {
    window.localStorage.setItem(
      storageKey("진료실"),
      JSON.stringify({ columns: [300, 400, 500], rows: {} })
    );
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("localStorage 가 예외를 던져도 기본값을 돌려준다", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadLayout("진료실")).toEqual(DEFAULT_LAYOUTS["진료실"]);
  });

  it("saveLayout 이 예외를 던져도 호출자가 죽지 않는다", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => saveLayout("진료실", DEFAULT_LAYOUTS["진료실"])).not.toThrow();
  });
});

describe("toTrackList", () => {
  it("null 은 1fr 로, 숫자는 px 로 바꾸고 사이에 핸들 자리를 넣는다", () => {
    expect(toTrackList([300, null, 350], MIN_COLUMN_PX)).toBe(
      "minmax(200px, 300px) 6px minmax(200px, 1fr) 6px minmax(200px, 350px)"
    );
  });

  it("트랙이 하나면 핸들 자리가 없다", () => {
    expect(toTrackList([null], MIN_ROW_PX)).toBe("minmax(120px, 1fr)");
  });
});

describe("applyDelta", () => {
  it("인접한 두 트랙이 크기를 주고받는다", () => {
    expect(applyDelta([300, 400, null], 0, 50, MIN_COLUMN_PX, 1400)).toEqual([
      350, 350, null,
    ]);
  });

  it("최소값 아래로는 내려가지 않는다", () => {
    expect(applyDelta([300, 400, null], 0, -500, MIN_COLUMN_PX, 1400)).toEqual([
      200, 500, null,
    ]);
  });

  it("이웃이 1fr 이면 그 트랙만 바뀐다 — 1fr 이 나머지를 흡수한다", () => {
    expect(applyDelta([300, null, 350], 0, 40, MIN_COLUMN_PX, 1400)).toEqual([
      340, null, 350,
    ]);
  });

  it("행에도 같은 규칙이 적용된다", () => {
    expect(applyDelta([200, null], 0, -100, MIN_ROW_PX, 800)).toEqual([
      120, null,
    ]);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/utils/__tests__/layoutStorage.test.ts`
Expected: FAIL — `Failed to resolve import "../layoutStorage"`

- [ ] **Step 3: 구현한다**

`apps/web/src/utils/layoutStorage.ts`:

```ts
// 대시보드 레이아웃 치수를 브라우저에 탭별로 보관한다(spec §4).
//
// **이 파일은 이 저장소의 fail-closed 원칙 대상이 아니다.**
// verification / llmStatus / renalGate 는 판정을 정직하게 표시하기 위해
// "모르면 안전한 쪽"을 택한다. 화면 치수는 그 부류가 아니다 — 손상된 값으로
// 화면을 깨뜨리는 것보다 기본 배치로 되돌리는 편이 낫다. 그래서 여기서는
// 의심스러우면 조용히 DEFAULT_LAYOUTS 로 떨어진다.
//
// DOM 에 의존하지 않는다. 계정별 서버 저장이 필요해지면 이 파일의 뒷단만
// 바꾸면 되도록 순수 함수로 분리해 둔다(spec §7).

export type TabId = "환자접수" | "진료실" | "진단서";

/** `null` 은 "남는 공간을 차지한다"(`1fr`). 각 축에 최소 하나는 있어야 한다. */
export type Track = number | null;

export type LayoutState = {
  columns: Track[];
  /** 열 키(`left`/`middle`/`right`) → 그 열의 행 트랙 */
  rows: Record<string, Track[]>;
};

export const MIN_COLUMN_PX = 200;
export const MIN_ROW_PX = 120;

/**
 * 핸들도 그리드 항목이라 트랙 하나를 차지한다. 트랙 사이마다 이 폭이 끼므로
 * `grid-template-*` 의 항목 수는 `패널 수 * 2 - 1` 이다. CSS 폴백값도 같은
 * 모양이어야 한다 — 안 그러면 변수가 붙고 안 붙고에 따라 열 수가 달라진다.
 */
export const HANDLE_TRACK_PX = 6;

const KEY_PREFIX = "bitcomputer.layout.v1.";

/** 탭 → 저장 키에 쓸 ASCII 슬러그. 한글 키를 그대로 쓰지 않는다. */
const TAB_SLUG: Record<TabId, string> = {
  환자접수: "general",
  진료실: "clinic",
  진단서: "certificate",
};

// 폴백값은 page.module.css 의 현재 하드코딩 값과 같아야 한다. 다르면
// 저장값이 없는 사용자에게 배치가 갑자기 바뀐다.
export const DEFAULT_LAYOUTS: Record<TabId, LayoutState> = {
  환자접수: {
    columns: [300, null, null],
    rows: { left: [null, null], right: [null, null] },
  },
  진료실: {
    columns: [300, null, 350],
    rows: { left: [null, null], middle: [null, null, null], right: [null, null] },
  },
  진단서: {
    columns: [280, null, null],
    rows: { middle: [null, null] },
  },
};

export function storageKey(tab: TabId): string {
  return KEY_PREFIX + TAB_SLUG[tab];
}

function isTrack(value: unknown): value is Track {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

/** 트랙 배열이 쓸 수 있는 상태인가. 길이·타입·최소값·1fr 존재를 본다. */
function isUsable(tracks: unknown, expectedLength: number, min: number): tracks is Track[] {
  if (!Array.isArray(tracks) || tracks.length !== expectedLength) return false;
  if (!tracks.every(isTrack)) return false;
  if (!tracks.some((t) => t === null)) return false; // 1fr 이 하나도 없다
  return tracks.every((t) => t === null || t >= min);
}

function matchesShape(value: unknown, fallback: LayoutState): value is LayoutState {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<LayoutState>;
  if (!isUsable(candidate.columns, fallback.columns.length, MIN_COLUMN_PX)) return false;
  if (typeof candidate.rows !== "object" || candidate.rows === null) return false;
  const rows = candidate.rows as Record<string, unknown>;
  const keys = Object.keys(fallback.rows);
  if (Object.keys(rows).length !== keys.length) return false;
  return keys.every((k) => isUsable(rows[k], fallback.rows[k].length, MIN_ROW_PX));
}

export function loadLayout(tab: TabId): LayoutState {
  const fallback = DEFAULT_LAYOUTS[tab];
  try {
    const raw = window.localStorage.getItem(storageKey(tab));
    if (!raw) return fallback;
    const parsed: unknown = JSON.parse(raw);
    return matchesShape(parsed, fallback) ? parsed : fallback;
  } catch {
    // 파싱 실패, 사생활 보호 모드, 저장소 차단 — 전부 같은 답이다.
    return fallback;
  }
}

export function saveLayout(tab: TabId, state: LayoutState): void {
  try {
    window.localStorage.setItem(storageKey(tab), JSON.stringify(state));
  } catch {
    // 저장 실패가 화면을 죽이면 안 된다. 이번 세션에서만 유지된다.
  }
}

export function clearLayout(tab: TabId): void {
  try {
    window.localStorage.removeItem(storageKey(tab));
  } catch {
    // 위와 같다.
  }
}

/**
 * 트랙 배열을 `grid-template-*` 문자열로 바꾼다.
 *
 * `minmax(min, ...)` 로 감싸는 이유: 내용이 큰 패널이 트랙을 최소값 아래로
 * 밀어내는 것을 막는다. CSS 만으로 하한을 지켜, 드래그 클램프가 뚫려도
 * 레이아웃이 무너지지 않는다.
 */
export function toTrackList(tracks: Track[], min: number): string {
  return tracks
    .map((t) => `minmax(${min}px, ${t === null ? "1fr" : `${t}px`})`)
    .join(` ${HANDLE_TRACK_PX}px `);
}

/**
 * `index` 와 `index + 1` 사이 경계를 `deltaPx` 만큼 민다.
 *
 * 두 트랙이 크기를 주고받되, `1fr`(null) 트랙은 값을 갖지 않으므로 건드리지
 * 않는다 — 남는 공간을 흡수하는 것이 그 역할이다. 그래서 이웃이 `1fr` 이면
 * 이쪽 트랙만 바뀐다.
 */
export function applyDelta(
  tracks: Track[],
  index: number,
  deltaPx: number,
  min: number,
  containerPx: number
): Track[] {
  const next = [...tracks];
  const a = next[index];
  const b = next[index + 1];
  if (a === null && b === null) return next; // 둘 다 1fr — 경계에 의미가 없다

  if (a !== null && b !== null) {
    const total = a + b;
    const clamped = Math.max(min, Math.min(total - min, a + deltaPx));
    next[index] = clamped;
    next[index + 1] = total - clamped;
    return next;
  }

  if (a !== null) {
    // 이웃이 1fr — 컨테이너를 넘지 않는 선에서 이쪽만 키우고 줄인다.
    const others = next.reduce<number>(
      (sum, t, i) => (i === index || t === null ? sum : sum + t),
      0
    );
    const upper = Math.max(min, containerPx - others - min);
    next[index] = Math.max(min, Math.min(upper, a + deltaPx));
    return next;
  }

  // a 가 1fr 이고 b 가 고정 — 경계를 밀면 b 가 반대로 움직인다.
  const others = next.reduce<number>(
    (sum, t, i) => (i === index + 1 || t === null ? sum : sum + t),
    0
  );
  const upper = Math.max(min, containerPx - others - min);
  next[index + 1] = Math.max(min, Math.min(upper, (b as number) - deltaPx));
  return next;
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/utils/__tests__/layoutStorage.test.ts`
Expected: PASS, 15 tests

- [ ] **Step 5: 커밋**

```bash
git add apps/web/src/utils/layoutStorage.ts apps/web/src/utils/__tests__/layoutStorage.test.ts
git commit -m "feat(web): 대시보드 레이아웃 저장 계층

탭별 치수를 localStorage 에 보관한다. 순수 함수라 DOM 없이 테스트되고,
계정별 서버 저장이 필요해지면 뒷단만 바꾸면 된다.

null 은 1fr 을 뜻하고 각 축에 최소 하나 있어야 한다. 모든 트랙에 픽셀을
박으면 창 크기가 바뀔 때 합계가 안 맞는다. 유효성 검사가 그 불변식까지
확인하고, 깨지면 기본값으로 떨어진다.

레이아웃은 이 저장소의 fail-closed 원칙 대상이 아니다. 판정을 표시하는
필드들과 달리, 손상된 값으로 화면을 깨뜨리는 것보다 기본 배치로 되돌리는
편이 낫다. 그 구분을 파일 주석에 남겼다."
```

---

## Task 2: 훅

**Files:**
- Create: `apps/web/src/hooks/useResizableLayout.ts`
- Test: `apps/web/src/hooks/__tests__/useResizableLayout.test.tsx`

**Interfaces:**
- Consumes: Task 1 의 `TabId`, `Track`, `LayoutState`, `MIN_COLUMN_PX`, `MIN_ROW_PX`, `DEFAULT_LAYOUTS`, `loadLayout`, `saveLayout`, `clearLayout`, `toTrackList`, `applyDelta`
- Produces:
  - `RESIZE_MIN_VIEWPORT = 1025`
  - `useResizableLayout(tab: TabId): { enabled: boolean; columnStyle: React.CSSProperties; rowStyle(columnKey: string): React.CSSProperties; resizeColumn(index: number, deltaPx: number, containerPx: number): void; resizeRow(columnKey: string, index: number, deltaPx: number, containerPx: number): void; reset(): void }`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`apps/web/src/hooks/__tests__/useResizableLayout.test.tsx`:

```tsx
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_LAYOUTS, loadLayout, saveLayout, storageKey } from "../../utils/layoutStorage";
import { useResizableLayout } from "../useResizableLayout";

function setViewport(width: number) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: width >= 1025,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
  setViewport(1400);
});

describe("복원", () => {
  it("저장값이 있으면 그 값으로 트랙을 만든다", () => {
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    const { result } = renderHook(() => useResizableLayout("진료실"));
    expect(result.current.columnStyle["--col-tracks" as never]).toContain("420px");
  });

  it("저장값이 없으면 기본 배치를 쓴다", () => {
    const { result } = renderHook(() => useResizableLayout("진료실"));
    expect(result.current.columnStyle["--col-tracks" as never]).toContain("300px");
  });
});

describe("뷰포트 가드", () => {
  it("1024px 이하에서는 변수를 붙이지 않는다 — 미디어쿼리가 살아나야 한다", () => {
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    setViewport(900);
    const { result } = renderHook(() => useResizableLayout("진료실"));
    expect(result.current.enabled).toBe(false);
    expect(result.current.columnStyle).toEqual({});
  });

  it("좁은 화면에서도 저장값을 지우지 않는다", () => {
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    setViewport(900);
    renderHook(() => useResizableLayout("진료실"));
    expect(loadLayout("진료실").columns).toEqual([420, null, 350]);
  });
});

describe("조절", () => {
  it("열 델타가 반영되고 저장된다", () => {
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeColumn(0, 60, 1400));
    expect(result.current.columnStyle["--col-tracks" as never]).toContain("360px");
    expect(loadLayout("진료실").columns[0]).toBe(360);
  });

  it("행 델타가 그 열에만 반영된다", () => {
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeRow("middle", 0, 40, 900));
    expect(loadLayout("진료실").rows.middle[0]).not.toBeNull();
    expect(loadLayout("진료실").rows.left).toEqual(DEFAULT_LAYOUTS["진료실"].rows.left);
  });

  it("reset 은 그 탭 키만 지운다", () => {
    saveLayout("진단서", { ...DEFAULT_LAYOUTS["진단서"], columns: [400, null, null] });
    const { result } = renderHook(() => useResizableLayout("진료실"));
    act(() => result.current.resizeColumn(0, 60, 1400));
    act(() => result.current.reset());
    expect(window.localStorage.getItem(storageKey("진료실"))).toBeNull();
    expect(loadLayout("진단서").columns).toEqual([400, null, null]);
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/hooks/__tests__/useResizableLayout.test.tsx`
Expected: FAIL — `Failed to resolve import "../useResizableLayout"`

- [ ] **Step 3: 구현한다**

`apps/web/src/hooks/useResizableLayout.ts`:

```ts
"use client";

import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  DEFAULT_LAYOUTS,
  MIN_COLUMN_PX,
  MIN_ROW_PX,
  applyDelta,
  clearLayout,
  loadLayout,
  saveLayout,
  toTrackList,
  type LayoutState,
  type TabId,
} from "../utils/layoutStorage";

/**
 * 이 폭보다 좁으면 저장값을 적용하지 않는다.
 *
 * 인라인 CSS 변수는 미디어쿼리를 이긴다. 넓은 화면에서 정한 값을 좁은
 * 화면에 그대로 씌우면 기존 반응형 규칙이 전부 무력해진다(spec §5.2).
 * 변수를 붙이지 않으면 CSS 폴백값 = 미디어쿼리 결과가 살아난다.
 */
export const RESIZE_MIN_VIEWPORT = 1025;

export function useResizableLayout(tab: TabId) {
  const [state, setState] = useState<LayoutState>(() => DEFAULT_LAYOUTS[tab]);
  const [enabled, setEnabled] = useState(false);

  // localStorage 와 matchMedia 는 서버에 없다. 첫 렌더는 기본값으로 하고
  // 마운트 후 복원한다 — 그래야 hydration 불일치가 나지 않는다.
  useEffect(() => {
    setState(loadLayout(tab));
  }, [tab]);

  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${RESIZE_MIN_VIEWPORT}px)`);
    const sync = () => setEnabled(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const commit = useCallback(
    (next: LayoutState) => {
      setState(next);
      saveLayout(tab, next);
    },
    [tab]
  );

  const resizeColumn = useCallback(
    (index: number, deltaPx: number, containerPx: number) => {
      setState((prev) => {
        const next = {
          ...prev,
          columns: applyDelta(prev.columns, index, deltaPx, MIN_COLUMN_PX, containerPx),
        };
        saveLayout(tab, next);
        return next;
      });
    },
    [tab]
  );

  const resizeRow = useCallback(
    (columnKey: string, index: number, deltaPx: number, containerPx: number) => {
      setState((prev) => {
        const tracks = prev.rows[columnKey];
        if (!tracks) return prev;
        const next = {
          ...prev,
          rows: {
            ...prev.rows,
            [columnKey]: applyDelta(tracks, index, deltaPx, MIN_ROW_PX, containerPx),
          },
        };
        saveLayout(tab, next);
        return next;
      });
    },
    [tab]
  );

  const reset = useCallback(() => {
    clearLayout(tab);
    setState(DEFAULT_LAYOUTS[tab]);
  }, [tab]);

  const columnStyle: CSSProperties = enabled
    ? ({ "--col-tracks": toTrackList(state.columns, MIN_COLUMN_PX) } as CSSProperties)
    : {};

  const rowStyle = useCallback(
    (columnKey: string): CSSProperties => {
      const tracks = state.rows[columnKey];
      if (!enabled || !tracks) return {};
      return { "--row-tracks": toTrackList(tracks, MIN_ROW_PX) } as CSSProperties;
    },
    [enabled, state.rows]
  );

  return { enabled, columnStyle, rowStyle, resizeColumn, resizeRow, reset, commit };
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/hooks/__tests__/useResizableLayout.test.tsx`
Expected: PASS, 7 tests

- [ ] **Step 5: 커밋**

```bash
git add apps/web/src/hooks/
git commit -m "feat(web): 레이아웃 조절 훅

저장 계층을 React 상태에 잇고 뷰포트 가드를 건다.

1024px 이하에서는 CSS 변수를 아예 붙이지 않는다. 인라인 변수가 미디어쿼리를
이기므로, 넓은 화면에서 정한 값을 좁은 화면에 씌우면 기존 반응형 규칙이
무력해진다. 변수가 없으면 CSS 폴백값 = 미디어쿼리 결과가 살아난다.
저장값 자체는 지우지 않아 넓은 화면으로 돌아가면 되살아난다.

복원을 useEffect 로 미루는 것은 localStorage 와 matchMedia 가 서버에 없어서다.
첫 렌더를 기본값으로 해야 hydration 불일치가 나지 않는다."
```

---

## Task 3: 핸들 컴포넌트

**Files:**
- Create: `apps/web/src/components/ResizeHandle.tsx`
- Create: `apps/web/src/components/ResizeHandle.module.css`
- Test: `apps/web/src/components/__tests__/ResizeHandle.test.tsx`

**Interfaces:**
- Consumes: 없음(델타를 콜백으로 넘길 뿐, 저장 계층을 모른다)
- Produces: `ResizeHandle` — props `{ orientation: "vertical" | "horizontal"; label: string; onDelta: (deltaPx: number) => void; keyStepPx?: number }`

`orientation="vertical"` 은 **열 사이 세로선**(좌우 너비 조절), `"horizontal"` 은 **행 사이 가로선**(위아래 높이 조절)이다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`apps/web/src/components/__tests__/ResizeHandle.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResizeHandle } from "../ResizeHandle";

function setup(orientation: "vertical" | "horizontal" = "vertical") {
  const onDelta = vi.fn();
  render(<ResizeHandle orientation={orientation} label="왼쪽 열 너비 조절" onDelta={onDelta} />);
  const handle = screen.getByRole("separator", { name: "왼쪽 열 너비 조절" });
  // jsdom 은 pointer capture 를 구현하지 않는다.
  (handle as HTMLElement).setPointerCapture = vi.fn();
  (handle as HTMLElement).releasePointerCapture = vi.fn();
  return { handle, onDelta };
}

describe("접근성", () => {
  it("separator 로 노출되고 포커스를 받는다", () => {
    const { handle } = setup();
    expect(handle).toHaveAttribute("tabindex", "0");
    expect(handle).toHaveAttribute("aria-orientation", "vertical");
  });
});

describe("드래그", () => {
  it("가로 이동량을 델타로 넘긴다", () => {
    const { handle, onDelta } = setup("vertical");
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 100, clientY: 0 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 140, clientY: 0 });
    expect(onDelta).toHaveBeenCalledWith(40);
  });

  it("세로 핸들은 세로 이동량을 쓴다", () => {
    const { handle, onDelta } = setup("horizontal");
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 0, clientY: 200 });
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 0, clientY: 170 });
    expect(onDelta).toHaveBeenCalledWith(-30);
  });

  it("누르지 않은 채 움직이면 아무 일도 없다", () => {
    const { handle, onDelta } = setup();
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 140 });
    expect(onDelta).not.toHaveBeenCalled();
  });

  it("떼고 나면 더 이상 반응하지 않는다", () => {
    const { handle, onDelta } = setup();
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 100 });
    fireEvent.pointerUp(handle, { pointerId: 1, clientX: 100 });
    onDelta.mockClear();
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 200 });
    expect(onDelta).not.toHaveBeenCalled();
  });
});

describe("키보드", () => {
  it("화살표로 조절된다", () => {
    const { handle, onDelta } = setup("vertical");
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(onDelta).toHaveBeenCalledWith(10);
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(onDelta).toHaveBeenCalledWith(-10);
  });

  it("세로 핸들은 위아래 화살표를 쓴다", () => {
    const { handle, onDelta } = setup("horizontal");
    fireEvent.keyDown(handle, { key: "ArrowDown" });
    expect(onDelta).toHaveBeenCalledWith(10);
  });

  it("관계없는 키는 무시한다", () => {
    const { handle, onDelta } = setup();
    fireEvent.keyDown(handle, { key: "a" });
    expect(onDelta).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run src/components/__tests__/ResizeHandle.test.tsx`
Expected: FAIL — `Failed to resolve import "../ResizeHandle"`

- [ ] **Step 3: 구현한다**

`apps/web/src/components/ResizeHandle.module.css`:

```css
/* 평소에는 gap 안에서 거의 드러나지 않고, 만질 수 있다는 것만 알린다. */
.handle {
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 2px;
  transition: background-color 120ms ease;
}

.handle:hover,
.handle:focus-visible {
  background: var(--border-strong);
}

.handle:focus-visible {
  outline: 2px solid var(--border-strong);
  outline-offset: 2px;
}

.vertical {
  cursor: col-resize;
  width: 6px;
  align-self: stretch;
  justify-self: center;
}

.horizontal {
  cursor: row-resize;
  height: 6px;
  justify-self: stretch;
  align-self: center;
}

/* 드래그 중 텍스트가 선택되는 것을 막는다. */
:global(body.isResizing) {
  user-select: none;
  cursor: grabbing;
}
```

`apps/web/src/components/ResizeHandle.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import styles from "./ResizeHandle.module.css";

const DEFAULT_KEY_STEP_PX = 10;

type Props = {
  /** `vertical` = 열 사이 세로선(좌우), `horizontal` = 행 사이 가로선(위아래) */
  orientation: "vertical" | "horizontal";
  label: string;
  onDelta: (deltaPx: number) => void;
  keyStepPx?: number;
};

/**
 * 경계 하나를 담당한다. **저장 계층을 모른다** — 이동량만 콜백으로 넘긴다.
 * 어떤 트랙이 얼마나 바뀔지는 호출자가 정한다.
 *
 * 드래그 전용 UI 는 접근성 관점에서 막힌 길이라 화살표 키도 받는다(spec §5.4).
 */
export function ResizeHandle({ orientation, label, onDelta, keyStepPx = DEFAULT_KEY_STEP_PX }: Props) {
  const lastRef = useRef<number | null>(null);

  // 드래그 도중 언마운트되면 body 클래스가 남는다.
  useEffect(() => () => document.body.classList.remove("isResizing"), []);

  const axisValue = useCallback(
    (e: PointerEvent<HTMLDivElement>) => (orientation === "vertical" ? e.clientX : e.clientY),
    [orientation]
  );

  const handlePointerDown = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      lastRef.current = axisValue(e);
      e.currentTarget.setPointerCapture?.(e.pointerId);
      document.body.classList.add("isResizing");
    },
    [axisValue]
  );

  const handlePointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (lastRef.current === null) return;
      const current = axisValue(e);
      const delta = current - lastRef.current;
      if (delta === 0) return;
      lastRef.current = current;
      onDelta(delta);
    },
    [axisValue, onDelta]
  );

  const endDrag = useCallback((e: PointerEvent<HTMLDivElement>) => {
    lastRef.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    document.body.classList.remove("isResizing");
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const decrease = orientation === "vertical" ? "ArrowLeft" : "ArrowUp";
      const increase = orientation === "vertical" ? "ArrowRight" : "ArrowDown";
      if (e.key !== decrease && e.key !== increase) return;
      e.preventDefault();
      onDelta(e.key === increase ? keyStepPx : -keyStepPx);
    },
    [keyStepPx, onDelta, orientation]
  );

  return (
    <div
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      tabIndex={0}
      className={`${styles.handle} ${styles[orientation]}`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={handleKeyDown}
    />
  );
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `cd apps/web && npx vitest run src/components/__tests__/ResizeHandle.test.tsx`
Expected: PASS, 8 tests

- [ ] **Step 5: 커밋**

```bash
git add apps/web/src/components/ResizeHandle.tsx apps/web/src/components/ResizeHandle.module.css apps/web/src/components/__tests__/ResizeHandle.test.tsx
git commit -m "feat(web): 경계 드래그 핸들

이동량만 콜백으로 넘기고 저장 계층은 모른다. 어떤 트랙이 얼마나 바뀔지는
호출자가 정한다.

화살표 키도 받는다. 드래그 전용 UI 는 접근성 관점에서 막힌 길이고, 의료
현장에서 마우스만 강제하면 안 된다.

pointer capture 는 optional call 로 부른다 - jsdom 이 구현하지 않아 테스트가
그것 때문에 깨지면 안 된다."
```

---

## Task 4: CSS 를 변수로 바꾸고 열을 grid 로

**Files:**
- Modify: `apps/web/src/app/(dashboard)/dashboard/page.module.css`

**Interfaces:**
- Consumes: Task 2 가 내보내는 `--col-tracks`, `--row-tracks` 변수 이름
- Produces: 변수가 없을 때 현재와 동일한 배치

이 태스크는 시각 회귀가 관심사라 단위 테스트가 아니라 **브라우저 확인**으로 검증한다. spec §7 이 "flex→grid 전환이 배치를 미묘하게 바꿀 수 있고 테스트가 대신 못 한다"고 적은 그 지점이다.

- [ ] **Step 1: 변경 전 배치를 기록한다**

```bash
cd infra && docker compose up -d frontend
```

http://localhost:3000 에서 세 탭(환자접수·진료실·진단서)을 열어 각각 스크린샷을 남긴다. 이것이 비교 기준이다.

- [ ] **Step 2: 그리드 치수를 변수로 바꾼다**

`page.module.css` 의 세 그리드를 이렇게 고친다. **폴백값은 지금 값 그대로다.**

```css
.contentGrid {
  display: grid;
  grid-template-columns: var(--col-tracks, 300px 1fr 1fr);
  gap: var(--space-4);
  height: 100%;
  min-height: 600px;
}

.contentGridClinic {
  display: grid;
  grid-template-columns: var(--col-tracks, 300px 1fr 350px);
  gap: var(--space-4);
  height: 100%;
  min-height: 600px;
}

.contentGridCertificate {
  display: grid;
  grid-template-columns: var(--col-tracks, 280px 1fr 1fr);
  gap: var(--space-4);
  height: 100%;
  min-height: 600px;
}
```

미디어쿼리 블록(1200px / 1024px / 768px)은 **그대로 둔다.** 훅이 1024px 이하에서 변수를 붙이지 않으므로 폴백값이 살아나고, 그 폴백을 미디어쿼리가 덮어쓴다.

- [ ] **Step 3: 열을 grid 로 바꾼다**

패널이 둘 이상인 열만 바꾼다. 단일 패널 열(`middleColumn`, `certificateRightColumn`)은 건드리지 않는다.

```css
.leftColumn {
  display: grid;
  grid-template-rows: var(--row-tracks, 1fr 1fr);
  gap: var(--space-4);
  min-height: 0;
}

.rightColumn {
  display: grid;
  grid-template-rows: var(--row-tracks, 1fr 1fr);
  gap: var(--space-4);
  min-height: 0;
}

.clinicMiddleColumn {
  display: grid;
  grid-template-rows: var(--row-tracks, 1fr 1fr 1fr);
  gap: var(--space-4);
  min-height: 0;
}

.clinicRightColumn {
  display: grid;
  grid-template-rows: var(--row-tracks, 1fr 1fr);
  gap: var(--space-4);
  min-height: 0;
}

.certificateCenterColumn {
  display: grid;
  grid-template-rows: var(--row-tracks, 1fr 1fr);
  gap: var(--space-4);
  min-height: 0;
  height: 100%;
}
```

`min-height: 0` 이 없으면 grid 자식이 내용 크기 아래로 줄지 않아 트랙을 줄여도 패널이 안 줄어든다.

- [ ] **Step 4: 브라우저에서 세 탭을 비교한다**

```bash
cd infra && docker compose build frontend && docker compose up -d frontend
```

Step 1 의 스크린샷과 나란히 놓고 본다. **패널이 잘리거나 겹치거나 세로로 늘어지지 않아야 한다.** flex 의 `flex-shrink: 1` 과 grid 트랙 `auto` 가 항상 같지 않으므로, 다르면 해당 열의 폴백 트랙을 `auto 1fr` 같은 형태로 조정한다(어느 패널이 고정 높이를 원하는지에 따라 다르다).

- [ ] **Step 5: 커밋**

```bash
git add "apps/web/src/app/(dashboard)/dashboard/page.module.css"
git commit -m "refactor(web): 대시보드 그리드 치수를 CSS 변수로

폴백값을 지금 값 그대로 둬서 변수가 없으면 동작이 같다. 미디어쿼리는
건드리지 않는다 - 훅이 1024px 이하에서 변수를 붙이지 않으므로 폴백이
살아나고 그것을 미디어쿼리가 덮는다.

패널이 둘 이상인 열을 flex 에서 grid 로 바꿨다. flex-basis 로는 핸들을
20px 끌었을 때 패널이 20px 커진다는 보장이 없다 - flex-grow 와 gap 과 내용
높이가 섞인다. grid 는 트랙 크기가 곧 값이다.

min-height: 0 이 없으면 grid 자식이 내용 크기 아래로 줄지 않아 트랙을 줄여도
패널이 안 줄어든다.

세 탭을 브라우저에서 변경 전후로 비교했다."
```

---

## Task 5: 페이지 배선

**Files:**
- Modify: `apps/web/src/app/(dashboard)/dashboard/page.tsx`
- Modify: `apps/web/src/app/(dashboard)/dashboard/page.module.css` (버튼 스타일)
- Test: `apps/web/src/app/(dashboard)/dashboard/__tests__/layout-resize.test.tsx`

**Interfaces:**
- Consumes: Task 2 의 `useResizableLayout`, Task 3 의 `ResizeHandle`
- Produces: 없음(최종 태스크)

`page.tsx:136` 의 `activeMenu` 가 곧 `TabId` 다 — `"환자접수"` / `"진료실"` / `"진단서"`.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`apps/web/src/app/(dashboard)/dashboard/__tests__/layout-resize.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "../page";
import { DEFAULT_LAYOUTS, loadLayout, saveLayout, storageKey } from "@/utils/layoutStorage";

vi.mock("@/services/auth", () => ({
  getCurrentUser: vi.fn().mockResolvedValue({ role: "DOCTOR", employeeId: 1 }),
}));

function setWideViewport() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: true,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }));
}

beforeEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
  setWideViewport();
});

describe("대시보드 레이아웃 조절", () => {
  it("열 경계 핸들이 렌더된다", async () => {
    render(<DashboardPage />);
    const handles = await screen.findAllByRole("separator");
    expect(handles.length).toBeGreaterThan(0);
  });

  it("기본 배치로 버튼이 그 탭 키만 지운다", async () => {
    saveLayout("환자접수", { ...DEFAULT_LAYOUTS["환자접수"], columns: [420, null, null] });
    saveLayout("진료실", { ...DEFAULT_LAYOUTS["진료실"], columns: [420, null, 350] });
    render(<DashboardPage />);
    fireEvent.click(await screen.findByRole("button", { name: "기본 배치로" }));
    expect(window.localStorage.getItem(storageKey("환자접수"))).toBeNull();
    expect(loadLayout("진료실").columns).toEqual([420, null, 350]);
  });

  it("저장이 실패해도 화면이 죽지 않는다", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    render(<DashboardPage />);
    const handle = (await screen.findAllByRole("separator"))[0];
    expect(() => fireEvent.keyDown(handle, { key: "ArrowRight" })).not.toThrow();
    expect(await screen.findByRole("button", { name: "기본 배치로" })).toBeInTheDocument();
  });
});
```

`@/services/auth` 의 실제 export 이름이 다르면 `apps/web/src/app/(dashboard)/dashboard/page.tsx` 의 import 를 보고 맞춘다. 기존 `Diagnosis.test.tsx` 가 같은 방식으로 목을 만든다.

- [ ] **Step 2: 실패를 확인한다**

Run: `cd apps/web && npx vitest run "src/app/(dashboard)/dashboard/__tests__/layout-resize.test.tsx"`
Expected: FAIL — `separator` 역할을 가진 요소를 찾지 못한다

- [ ] **Step 3: 훅을 배선한다**

`page.tsx` 상단 import 에 추가:

```tsx
import { useRef } from "react";
import { ResizeHandle } from "@/components/ResizeHandle";
import { useResizableLayout } from "@/hooks/useResizableLayout";
import type { TabId } from "@/utils/layoutStorage";
```

`renderContent` 정의(`:431`) 바로 위에 추가:

```tsx
  const layout = useResizableLayout(activeMenu as TabId);
  const gridRef = useRef<HTMLDivElement>(null);

  // 델타를 트랙에 반영하려면 컨테이너 실제 크기가 필요하다. 1fr 트랙의
  // 상한을 계산하는 데 쓴다(layoutStorage.applyDelta 참고).
  const gridWidth = () => gridRef.current?.getBoundingClientRect().width ?? 0;
```

- [ ] **Step 4: 그리드에 style 과 핸들을 붙인다**

`환자접수` 분기(`:434`)를 이렇게 바꾼다. 세 탭 모두 같은 모양이다.

```tsx
        <div className={styles.contentGrid} style={layout.columnStyle} ref={gridRef}>
          <div className={styles.leftColumn} style={layout.rowStyle("left")}>
            <SpecialNote />
            <History /* 기존 props 그대로 */ />
          </div>
          {layout.enabled && (
            <ResizeHandle
              orientation="vertical"
              label="왼쪽 열 너비 조절"
              onDelta={(d) => layout.resizeColumn(0, d, gridWidth())}
            />
          )}
          <div className={styles.middleColumn}>
            <PatientForm ref={patientFormRef} />
          </div>
          {layout.enabled && (
            <ResizeHandle
              orientation="vertical"
              label="가운데 열 너비 조절"
              onDelta={(d) => layout.resizeColumn(1, d, gridWidth())}
            />
          )}
          <div className={styles.rightColumn} style={layout.rowStyle("right")}>
            <WaitingStatus /* 기존 props 그대로 */ />
            <MedicalInfo ref={medicalInfoRef} />
          </div>
        </div>
```

**핸들이 그리드 항목이 되므로 열 개수가 3에서 5로 늘어난다.** 트랙 목록에 핸들 폭을 끼워야 한다. `layoutStorage.toTrackList` 를 그대로 쓰되, `page.module.css` 에서 그리드를 이렇게 바꾼다:

```css
.contentGrid {
  display: grid;
  grid-template-columns: var(--col-tracks, 300px 6px 1fr 6px 1fr);
  gap: var(--space-4);
  height: 100%;
  min-height: 600px;
}
```

`toTrackList` 는 Task 1 에서 이미 트랙 사이에 `HANDLE_TRACK_PX`(6px)를 끼우도록 만들어져 있다. **CSS 폴백값을 같은 모양으로 맞추기만 하면 된다** — 안 그러면 변수가 붙고 안 붙고에 따라 열 수가 달라진다.

행도 같다. 패널이 둘인 열은 `--row-tracks, 1fr 6px 1fr`, 셋인 열은 `1fr 6px 1fr 6px 1fr` 이 폴백이 된다. Task 4 에서 넣은 폴백값을 그에 맞춰 고친다.

- [ ] **Step 5: 행 핸들과 "기본 배치로" 버튼을 넣는다**

패널이 둘 이상인 열의 패널 사이에 넣는다. 예를 들어 `leftColumn`:

```tsx
          <div className={styles.leftColumn} style={layout.rowStyle("left")}>
            <SpecialNote />
            {layout.enabled && (
              <ResizeHandle
                orientation="horizontal"
                label="특이사항 높이 조절"
                onDelta={(d) => layout.resizeRow("left", 0, d, gridRef.current?.getBoundingClientRect().height ?? 0)}
              />
            )}
            <History /* 기존 props 그대로 */ />
          </div>
```

버튼은 `contentArea`(`:558`) 안, 그리드 위에 둔다:

```tsx
          <div className={styles.contentArea}>
            {layout.enabled && (
              <div className={styles.layoutBar}>
                <button type="button" className={styles.resetLayout} onClick={layout.reset}>
                  기본 배치로
                </button>
              </div>
            )}
            {renderContent()}
          </div>
```

`page.module.css` 에 추가:

```css
.layoutBar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-2);
}

.resetLayout {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: var(--space-1) var(--space-2);
  font-size: 0.8rem;
  cursor: pointer;
}

.resetLayout:hover {
  border-color: var(--border-strong);
}
```

- [ ] **Step 6: 전체 스위트와 타입 검사**

```bash
cd apps/web
npx vitest run
npx tsc --noEmit
```

Expected: 모두 통과. `tsc` 무오류.

- [ ] **Step 7: 브라우저에서 확인한다**

```bash
cd infra && docker compose build frontend && docker compose up -d frontend
```

http://localhost:3000 에서 확인할 것:

1. 세 탭 각각에서 열 경계를 끌면 너비가 바뀐다
2. 패널 경계를 끌면 높이가 바뀐다
3. 새로고침해도 배치가 남는다
4. 탭을 바꾸면 그 탭의 배치가 따로 적용된다
5. "기본 배치로" 를 누르면 그 탭만 돌아간다
6. 창을 1024px 이하로 줄이면 핸들이 사라지고 기존 반응형 배치가 나온다. 다시 넓히면 저장한 배치가 돌아온다
7. `Tab` 으로 핸들에 포커스가 가고 화살표로 조절된다

- [ ] **Step 8: 커밋**

```bash
git add "apps/web/src/app/(dashboard)/dashboard/"
git commit -m "feat(web): 대시보드 열·패널 크기 조절 배선

세 탭의 열 경계와 패널 경계에 핸들을 넣고 activeMenu 를 탭 키로 쓴다.

핸들이 그리드 항목이 되므로 트랙 목록에 핸들 폭(6px)을 끼운다. toTrackList
가 그 자리를 만들고, CSS 폴백값도 같은 모양이어야 한다.

기본 배치로 버튼은 그 탭 키만 지운다. 다른 탭 설정은 남는다.

브라우저에서 일곱 가지를 확인했다 - 열/행 드래그, 새로고침 후 유지, 탭별
분리, 되돌리기, 1024px 경계에서 핸들이 사라지고 저장값이 되살아나는 것,
키보드 조작."
```

---

## Self-Review

**Spec 커버리지**

| Spec 절 | 태스크 |
|---|---|
| §1 범위(대시보드 한 페이지, 단일 패널 열 제외) | Task 4 Step 3, Task 5 Step 4 |
| §2 결정(열+행, localStorage, 탭별, 드래그) | Task 1~5 전체 |
| §3.1 CSS 변수화 | Task 4 Step 2 |
| §3.2 flex→grid | Task 4 Step 3 |
| §3.3 새 파일 셋 | Task 1·2·3 |
| §4.1 저장 형태·키 | Task 1 |
| §4.2 `null` = `1fr` 불변식 | Task 1 (`isUsable` 의 `some(t => t === null)`) |
| §4.3 버전·실패 처리 | Task 1 |
| §5.1 최소 크기 | Task 1 (`MIN_*`, `applyDelta` 클램프, `minmax()`) |
| §5.2 반응형 충돌 | Task 2 (`RESIZE_MIN_VIEWPORT`) |
| §5.3 되돌리기 | Task 2 `reset`, Task 5 Step 5 |
| §5.4 키보드 | Task 3 |
| §5.5 시각 표시 | Task 3 CSS |
| §6 테스트·변이 | 각 태스크 Step 1, 아래 변이 표 |
| §7 flex→grid 시각 확인 | Task 4 Step 1·4 |

**변이 검증** (Task 5 Step 6 이후 실행)

| 변이 | 빨개져야 할 테스트 |
|---|---|
| `isUsable` 에서 `some(t => t === null)` 제거 | `1fr 트랙이 하나도 없으면` |
| `matchesShape` 의 길이 검사 제거 | `열 개수가 안 맞으면` |
| `applyDelta` 의 `Math.max(min, ...)` 제거 | `최소값 아래로는 내려가지 않는다` |
| `useResizableLayout` 의 `enabled` 가드 제거 | `1024px 이하에서는 변수를 붙이지 않는다` |
| `reset` 이 모든 키를 지우게 변경 | `reset 은 그 탭 키만 지운다` |

각 변이는 파일 복사로 백업하고 복사로 복원한다. **`git checkout --` 이나 `git stash` 를 쓰지 않는다** — 이 저장소에서 그렇게 하다 커밋 안 된 작업을 통째로 잃은 적이 있다. 복원 후 `diff` 로 확인하고 `git status --porcelain` 이 깨끗한지 본다.

**주의: 다른 세션이 `apps/web` 을 동시에 만진다.** `Diagnosis.tsx` 와 `utils/renalGateNotice.ts` 쪽이며 이 계획과 파일이 겹치지 않는다. 착수 전 `git log --oneline -3` 으로 `main` 이 움직였는지 확인한다.
