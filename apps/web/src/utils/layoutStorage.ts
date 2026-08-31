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

/**
 * 행 트랙 배열이 쓸 수 있는 상태인가. 열과 달리 행 키(`left`/`middle`/`right`)는
 * 탭마다 일부만 저장될 수 있어 길이나 키 구성을 기본값과 맞춰 요구하지 않는다
 * — 존재하는 각 배열이 축 하나로서 유효한지(타입·최소값·1fr 존재)만 본다.
 */
function isUsableRow(tracks: unknown, min: number): tracks is Track[] {
  if (!Array.isArray(tracks) || tracks.length === 0) return false;
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
  return Object.values(rows).every((tracks) => isUsableRow(tracks, MIN_ROW_PX));
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
