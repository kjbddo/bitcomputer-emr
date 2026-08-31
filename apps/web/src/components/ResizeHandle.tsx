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
  // 드래그를 시작한 포인터만 추적한다 — 다른 포인터의 move/up/cancel 은 무시해야 한다.
  const activeRef = useRef<{ pointerId: number; last: number } | null>(null);

  // 드래그 도중 언마운트되면 body 클래스가 남는다.
  useEffect(() => () => document.body.classList.remove("isResizing"), []);

  const axisValue = useCallback(
    (e: PointerEvent<HTMLDivElement>) => (orientation === "vertical" ? e.clientX : e.clientY),
    [orientation]
  );

  const handlePointerDown = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      activeRef.current = { pointerId: e.pointerId, last: axisValue(e) };
      e.currentTarget.setPointerCapture?.(e.pointerId);
      document.body.classList.add("isResizing");
    },
    [axisValue]
  );

  const handlePointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (activeRef.current === null || activeRef.current.pointerId !== e.pointerId) return;
      const current = axisValue(e);
      const delta = current - activeRef.current.last;
      if (delta === 0) return;
      activeRef.current.last = current;
      onDelta(delta);
    },
    [axisValue, onDelta]
  );

  const endDrag = useCallback((e: PointerEvent<HTMLDivElement>) => {
    if (activeRef.current === null || activeRef.current.pointerId !== e.pointerId) return;
    activeRef.current = null;
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
