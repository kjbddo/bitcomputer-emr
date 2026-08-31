"use client";

import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import {
  DEFAULT_LAYOUTS,
  HANDLE_TRACK_PX,
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
          columns: applyDelta(
            prev.columns,
            index,
            deltaPx,
            MIN_COLUMN_PX,
            usablePx(containerPx, prev.columns.length)
          ),
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
            [columnKey]: applyDelta(
              tracks,
              index,
              deltaPx,
              MIN_ROW_PX,
              usablePx(containerPx, tracks.length)
            ),
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
