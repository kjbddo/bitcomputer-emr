"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import styles from "./ResizeHandle.module.css";

const DEFAULT_KEY_STEP_PX = 10;

type Orientation = "vertical" | "horizontal";

type Props = {
  /** `vertical` = 열 사이 세로선(좌우), `horizontal` = 행 사이 가로선(위아래) */
  orientation: Orientation;
  label: string;
  onDelta: (deltaPx: number) => void;
  keyStepPx?: number;
};

/**
 * `aria-valuenow` 용 백분율을 구한다. 이건 "얼마나 움직일지" 를 정하는 게
 * 아니라 "지금 어디에 있는지" 를 스크린리더에 보고하는 것뿐이라, 이 파일이
 * 저장 계층을 모르고 이동량만 넘긴다는 설계 원칙과 충돌하지 않는다 — DOM 을
 * 읽기만 하고 그 결과를 어디에도 쓰지 않는다.
 *
 * 백분율 = 앞 형제 크기 / 부모 컨테이너 크기. `vertical` 이면 폭, `horizontal`
 * 이면 높이를 쓴다(핸들이 나누는 축과 같다).
 *
 * 앞 형제가 없거나(트랙이 하나뿐이라 나눌 대상이 없는 첫 핸들은 없지만,
 * 방어적으로 다룬다) 부모 크기가 0(레이아웃 계산 전, 혹은 숨겨진 탭)이면
 * 값을 알 수 없다. 임의의 숫자(예: 50)를 내면 실제 위치와 무관한 거짓
 * 정보가 되므로, 그 대신 `undefined` 를 돌려주고 호출부가 `aria-valuenow`
 * 자체를 생략하게 한다 — "모른다" 를 조용히 숨기지 않는다.
 */
function measureValueNow(handle: HTMLElement, orientation: Orientation): number | undefined {
  const sibling = handle.previousElementSibling;
  const parent = handle.parentElement;
  if (!sibling || !parent) return undefined;

  const siblingRect = sibling.getBoundingClientRect();
  const parentRect = parent.getBoundingClientRect();
  const siblingSize = orientation === "vertical" ? siblingRect.width : siblingRect.height;
  const parentSize = orientation === "vertical" ? parentRect.width : parentRect.height;
  if (parentSize <= 0) return undefined;

  return Math.round((siblingSize / parentSize) * 100);
}

/**
 * 경계 하나를 담당한다. **저장 계층을 모른다** — 이동량만 콜백으로 넘긴다.
 * 어떤 트랙이 얼마나 바뀔지는 호출자가 정한다.
 *
 * 드래그 전용 UI 는 접근성 관점에서 막힌 길이라 화살표 키도 받는다(spec §5.4).
 */
export function ResizeHandle({ orientation, label, onDelta, keyStepPx = DEFAULT_KEY_STEP_PX }: Props) {
  // 드래그를 시작한 포인터만 추적한다 — 다른 포인터의 move/up/cancel 은 무시해야 한다.
  const activeRef = useRef<{ pointerId: number; last: number } | null>(null);
  const handleRef = useRef<HTMLDivElement>(null);
  // 초기값을 50 같은 임의 숫자로 두지 않는다 — 실제로 측정하기 전까지는
  // "모른다" 는 뜻으로 undefined 를 유지한다.
  const [valueNow, setValueNow] = useState<number | undefined>(undefined);

  // 마운트 시 동기 측정 — 첫 페인트부터 정확한 값이 나가야 한다. useEffect
  // 를 쓰면 페인트 이후에 갱신되어 스크린리더가 잠깐 값 없는 상태를 읽을
  // 수 있다.
  useLayoutEffect(() => {
    const node = handleRef.current;
    if (!node) return;

    const measure = () => setValueNow(measureValueNow(node, orientation));
    measure();

    // ResizeObserver 가 없는 환경(jsdom 등)에서 던지지 않게 가드한다 —
    // window.matchMedia 무가드 호출로 이 브랜치가 한 번 데인 적이 있다
    // (useResizableLayout.ts 참고).
    if (typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(measure);
    // 드래그로 앞 형제 크기가 바뀌거나(직접 관찰 대상), 부모 컨테이너 자체
    // 크기가 바뀌어도(예: 창 리사이즈) 백분율은 따라와야 한다.
    if (node.parentElement) observer.observe(node.parentElement);
    if (node.previousElementSibling) observer.observe(node.previousElementSibling);

    return () => observer.disconnect();
  }, [orientation]);

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
      ref={handleRef}
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={valueNow}
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
