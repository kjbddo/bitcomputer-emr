// 대시보드 레이아웃 치수를 브라우저에 탭별로 보관한다(spec §4).
//
// **이 파일은 이 저장소의 fail-closed 원칙 대상이 아니다.**
// verification / llmStatus / renalGate 는 판정을 정직하게 표시하기 위해
// "모르면 안전한 쪽"을 택한다. 화면 치수는 그 부류가 아니다 — 손상된 값으로
// 화면을 깨뜨리는 것보다 기본 배치로 되돌리는 편이 낫다. 그래서 여기서는
// 의심스러우면 조용히 DEFAULT_LAYOUTS 로 떨어진다.
//
// **단, 손상값에 관대한 것과 계약 위반에 관대한 것은 다르다.** 깨진 JSON 을
// 기본값으로 받아넘기는 것은 UX 판단이지만, 3분할이던 열이 2분할로 바뀐 뒤
// 옛 3열 트랙을 그대로 받아들이는 것은 계약 위반이고 화면이 깨진다. 그래서
// matchesShape 는 키 집합과 배열 길이까지 본다 — 이 검증을 "레이아웃은
// fail-closed 대상이 아니니까" 라는 이유로 느슨하게 풀면 안 된다.
// (실제로 한 번 그렇게 풀었다가 되돌렸다.)
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
  /**
   * 패널이 하나뿐이라 행 경계가 없는 열(예: `middle`, `right`) → 그 패널의
   * 높이. `null` = 열 높이를 그대로 채운다(`1fr`). 이런 열이 없는 탭은 `{}`.
   */
  panels: Record<string, number | null>;
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
    panels: { middle: null },
  },
  진료실: {
    columns: [300, null, 350],
    rows: { left: [null, null], middle: [null, null, null], right: [null, null] },
    panels: {},
  },
  진단서: {
    columns: [280, null, null],
    rows: { middle: [null, null] },
    panels: { right: null },
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

/** `panels` 값 하나가 쓸 수 있는 상태인가 — `null` 또는 유한한 숫자. */
function isPanelValue(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function matchesShape(value: unknown, fallback: LayoutState): value is LayoutState {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<LayoutState>;
  if (!isUsable(candidate.columns, fallback.columns.length, MIN_COLUMN_PX)) return false;
  if (typeof candidate.rows !== "object" || candidate.rows === null) return false;
  const rows = candidate.rows as Record<string, unknown>;
  // 키 집합이 기본값과 정확히 같아야 한다 — 안 그러면 열이 하나 빠진 채로
  // 렌더링되거나(누락) 존재하지 않는 열의 값이 쓰레기로 섞여 들어온다.
  const fallbackKeys = Object.keys(fallback.rows);
  if (Object.keys(rows).length !== fallbackKeys.length) return false;
  if (
    !fallbackKeys.every((key) =>
      // 각 열의 배열 길이도 기본값(=현재 패널 수)과 정확히 같아야 한다 —
      // 안 그러면 패널이 추가/삭제된 뒤 옛 트랙 수가 새 패널 수와 안 맞는다(spec §4.3).
      isUsable(rows[key], fallback.rows[key].length, MIN_ROW_PX)
    )
  ) {
    return false;
  }
  // panels 도 rows 와 같은 원칙 — 키 집합이 기본값과 정확히 같아야 하고
  // (열이 하나 빠지거나 존재하지 않는 열이 쓰레기로 섞여 들어오는 것을 막는다),
  // 이 필드가 없는 옛 저장값(단일 패널 높이 조절이 생기기 전)은 형태 불일치로
  // 기본값으로 떨어뜨린다 — panels 도 다른 필드처럼 계약의 일부다.
  if (typeof candidate.panels !== "object" || candidate.panels === null) return false;
  const panels = candidate.panels as Record<string, unknown>;
  const fallbackPanelKeys = Object.keys(fallback.panels);
  if (Object.keys(panels).length !== fallbackPanelKeys.length) return false;
  return fallbackPanelKeys.every((key) => isPanelValue(panels[key]));
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
 *
 * 경계 양쪽이 둘 다 `1fr` 이면 — 이 경계를 끄는 것이야말로 사용자가 가장
 * 자주 하는 동작이므로 no-op 으로 두지 않는다. `1fr` 트랙은 남는 공간을
 * 정확히 균등 분할하므로 실측 없이 물질화(materialize)할 수 있다:
 * `each = (containerPx - 고정 트랙 합) / null 트랙 개수`. 물질화한 뒤에는
 * 기존 분기(아래)로 그대로 흘려보낸다 — 로직을 복제하지 않는다.
 *
 * 단, 이 축에는 `null` 이 최소 하나 남아야 한다는 불변식이 있다
 * (`matchesShape` 가 `some(t => t === null)` 로 검사한다 — 창 크기 변경 시
 * 흡수할 트랙이 없으면 레이아웃이 무너지기 때문). 그래서 `a`·`b` 를 둘 다
 * 물질화했을 때 이 축에 다른 `null` 이 하나도 안 남으면(2트랙 축이 정확히
 * 그 경우다), `b` 는 물질화하지 않고 `1fr` 로 남긴다 — 그러면 "a 는 고정,
 * 이웃은 1fr" 경로가 그대로 처리해, a 를 키우면 b 가 줄어드는 기대대로
 * 동작한다.
 */
/**
 * 고정 트랙 하나의 상한을 구할 때, 그 트랙을 제외한 나머지 `1fr`(null) 이웃들이
 * 각자 최소 `min` 픽셀을 요구한다는 사실을 반영한다.
 *
 * `excludeIndex` 는 지금 값을 정하고 있는 트랙 자신의 자리다. 그 트랙은 이 시점에
 * 아직 `null` 로 남아 있을 수 있으므로(물질화 직후 등) 셀 때 제외해야 한다 — 자기 자신을
 * 위한 공간은 상한 계산의 다른 항(`min` 하한)이 이미 보장하므로 여기서 또 빼면 이중으로
 * 빼게 된다.
 */
function reservedForOtherNullTracks(tracks: Track[], excludeIndex: number, min: number): number {
  const otherNullCount = tracks.filter((t, i) => i !== excludeIndex && t === null).length;
  return otherNullCount * min;
}

export function applyDelta(
  tracks: Track[],
  index: number,
  deltaPx: number,
  min: number,
  containerPx: number
): Track[] {
  const next = [...tracks];
  let a = next[index];
  let b = next[index + 1];

  if (a === null && b === null) {
    const fixedSum = next.reduce<number>((sum, t) => (t === null ? sum : sum + t), 0);
    const nullCount = next.filter((t) => t === null).length;
    const each = (containerPx - fixedSum) / nullCount;

    next[index] = each;
    a = each;

    const otherNullExists = next.some((t, i) => i !== index && i !== index + 1 && t === null);
    if (otherNullExists) {
      next[index + 1] = each;
      b = each;
    }
  }

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
    const reserved = reservedForOtherNullTracks(next, index, min);
    const upper = Math.max(min, containerPx - others - reserved);
    next[index] = Math.max(min, Math.min(upper, a + deltaPx));
    return next;
  }

  // a 가 1fr 이고 b 가 고정 — 경계를 밀면 b 가 반대로 움직인다.
  const others = next.reduce<number>(
    (sum, t, i) => (i === index + 1 || t === null ? sum : sum + t),
    0
  );
  const reserved = reservedForOtherNullTracks(next, index + 1, min);
  const upper = Math.max(min, containerPx - others - reserved);
  next[index + 1] = Math.max(min, Math.min(upper, (b as number) - deltaPx));
  return next;
}

/**
 * 패널이 하나뿐인 열의 패널 높이에 델타를 더한다. 트랙 배열이 아니라
 * 스칼라 하나라 `applyDelta` 는 쓸 수 없다(그리드 전체 높이를 다뤘던
 * `applyHeightDelta` 와 모양은 비슷하지만, 이건 열 하나의 패널 트랙이지
 * 그리드 전체가 아니다 — 그 기능은 되돌려졌다).
 *
 * `panel` 이 `null` 이면(아직 열 높이를 그대로 채운 상태, `1fr`) 실제 렌더
 * 높이인 `containerPx` 를 시작점으로 물질화한다 — `applyDelta` 가 1fr
 * 트랙을 다룰 때 쓰는 것과 같은 발상이다.
 *
 * 하한은 `MIN_ROW_PX`(패널 하나짜리 행이므로 행과 같은 최소값을 쓴다).
 * 상한은 `containerPx` — 가로 트랙과 달리 상한을 두지 않으면 패널이 열
 * 밖으로 넘쳐 아래 핸들 트랙이 열 바깥으로 밀려난다. 이 열에는 흡수할
 * 다른 트랙이 없으므로(핸들은 `auto` 로 자기 몫만 차지) 상한을 컨테이너
 * 자신의 높이로 못박아야 한다.
 */
export function applyPanelDelta(
  panel: number | null,
  deltaPx: number,
  containerPx: number
): number {
  const base = panel === null ? containerPx : panel;
  return Math.max(MIN_ROW_PX, Math.min(containerPx, base + deltaPx));
}
