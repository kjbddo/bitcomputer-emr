"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  DEFAULT_LAYOUTS,
  HANDLE_TRACK_PX,
  MIN_COLUMN_PX,
  MIN_ROW_PX,
  applyDelta,
  applyHeightDelta,
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

/**
 * `applyDelta` 의 `containerPx` 는 "고정 트랙 + 1fr 트랙" 만 채운다고 가정한다
 * (Task 1 리뷰에서 지적된 결함 — 핸들 트랙 몫을 빼지 않아 1fr 열이
 * MIN_*_PX 아래로 내려갈 수 있었다). 실제 컨테이너 폭은 핸들도 그리드
 * 항목이라 그만큼을 더 먹는다. 트랙 개수가 n 개면 핸들은 n-1 개이므로,
 * `applyDelta` 를 부르기 전에 그 몫을 미리 빼서 넘긴다 — `applyDelta`
 * 자체(Task 1, 18개 테스트로 이미 굳어짐)는 건드리지 않는다.
 */
function usablePx(containerPx: number, trackCount: number): number {
  return containerPx - HANDLE_TRACK_PX * Math.max(0, trackCount - 1);
}

export function useResizableLayout(tab: TabId) {
  const [state, setState] = useState<LayoutState>(() => DEFAULT_LAYOUTS[tab]);
  const [enabled, setEnabled] = useState(false);

  // localStorage 와 matchMedia 는 서버에 없다. 첫 렌더는 기본값으로 하고
  // 마운트 후 복원한다 — 그래야 hydration 불일치가 나지 않는다.
  useEffect(() => {
    setState(loadLayout(tab));
  }, [tab]);

  useEffect(() => {
    // matchMedia 가 없으면(구형 브라우저, 임베디드 웹뷰 등) 뷰포트를 판정할
    // 수 없다. 판정 불가를 "저장값 적용"으로 잘못 해석하면 좁은 화면을
    // 깨뜨릴 수 있지만(§5.2), "저장값 미적용"으로 해석해도 이번 렌더에
    // 저장값이 안 붙을 뿐이다 — 그래서 좁은 화면과 같은 편(비활성)으로
    // 떨어뜨린다. layoutStorage.ts 의 원칙과 같다: 손상/부재를 기본값으로
    // 조용히 흡수한다.
    if (typeof window.matchMedia !== "function") {
      setEnabled(false);
      return;
    }
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

  // resizeColumn/resizeRow 는 setState 를 함수형 업데이터로 부른다 — 드래그
  // 중 pointermove 가 렌더 사이사이에 연속으로 들어올 수 있어(ResizeHandle),
  // 클로저에 갇힌 state 를 참조하면 일부 델타가 씹힌다.
  //
  // 하지만 React 는 StrictMode(개발 모드)에서 이 업데이터 함수를 실제 커밋과
  // 무관하게 두 번 부른다(순수성 검증). saveLayout 을 업데이터 안에서
  // 부르면 그 부수효과도 두 번 일어난다 — 지금은 next.config.ts 가
  // reactStrictMode 를 안 켜서 안 보이지만, 켜지는 날 조용히 localStorage
  // 를 이중으로 쓰게 된다. 그래서 업데이터는 다음 state 계산만 하고,
  // 저장은 그 state 가 실제로 커밋된 뒤 이펙트에서 한 번만 한다.
  const pendingSaveRef = useRef(false);

  const resizeColumn = useCallback(
    (index: number, deltaPx: number, containerPx: number) => {
      pendingSaveRef.current = true;
      setState((prev) => ({
        ...prev,
        columns: applyDelta(
          prev.columns,
          index,
          deltaPx,
          MIN_COLUMN_PX,
          usablePx(containerPx, prev.columns.length)
        ),
      }));
    },
    [tab]
  );

  const resizeRow = useCallback(
    (columnKey: string, index: number, deltaPx: number, containerPx: number) => {
      pendingSaveRef.current = true;
      setState((prev) => {
        const tracks = prev.rows[columnKey];
        if (!tracks) {
          pendingSaveRef.current = false;
          return prev;
        }
        return {
          ...prev,
          rows: {
            ...prev.rows,
            [columnKey]: applyDelta(
              tracks,
              index,
              deltaPx,
              MIN_ROW_PX,
              usablePx(containerPx, tracks.length)
            ),
          },
        };
      });
    },
    [tab]
  );

  const resizeHeight = useCallback(
    (deltaPx: number, viewportPx: number) => {
      pendingSaveRef.current = true;
      setState((prev) => ({
        ...prev,
        height: applyHeightDelta(prev.height, deltaPx, viewportPx),
      }));
    },
    [tab]
  );

  useEffect(() => {
    if (!pendingSaveRef.current) return;
    pendingSaveRef.current = false;
    saveLayout(tab, state);
  }, [state, tab]);

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

  const gridHeightStyle: CSSProperties =
    enabled && typeof state.height === "number"
      ? ({ "--grid-height": `${state.height}px` } as CSSProperties)
      : {};

  return {
    enabled,
    columnStyle,
    rowStyle,
    gridHeightStyle,
    resizeColumn,
    resizeRow,
    resizeHeight,
    reset,
    commit,
  };
}
