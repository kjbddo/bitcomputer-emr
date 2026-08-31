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

  // 주 경로 — 매 커밋마다 동기 측정한다 (의존성 배열을 아예 생략).
  //
  // 관찰(ResizeObserver)에만 기대면, 관찰이 침묵하는 환경에서 값이 영원히
  // 옛 숫자로 남는다. 그 상태는 aria-valuenow 가 아예 없는 것보다 나쁘다 —
  // 스크린리더에 틀린 위치를 자신 있게 알려주기 때문이다(위 measureValueNow
  // 주석의 "거짓 정보보다 undefined" 원칙과 같은 이유). 드래그하면 이 핸들을
  // 소유한 page.tsx 가 리렌더되고 핸들도 함께 리렌더되므로, 매 렌더 측정하면
  // ResizeObserver 없이도 값이 항상 따라온다.
  //
  // 매 렌더 setState 는 보통 무한 루프를 의심할 패턴이라 왜 안전한지
  // 남긴다: React 는 새 상태가 Object.is 로 이전 상태와 같으면 그 지점에서
  // 리렌더를 건너뛴다(bail out). 즉 이 effect 는 실제로 값이 달라진
  // 렌더에서만 추가 리렌더를 일으키고, 값이 그대로인 렌더(예: 다른 이유로
  // 부모가 리렌더된 경우)에서는 setValueNow 가 아무 것도 바꾸지 않아 거기서
  // 수렴한다.
  //
  // eslint(react-hooks/exhaustive-deps) 는 의존성 배열이 없으면 무한 갱신
  // 사슬을 의심해 [orientation] 을 넣으라고 권한다. 여기서는 의도적으로
  // 생략한다 — [orientation] 을 넣으면 orientation 이 바뀔 때만 재측정하는
  // 옛 동작(관찰 침묵 시 값이 멈추는 버그)으로 되돌아간다. 안전성 근거는
  // 위 주석 참고.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const node = handleRef.current;
    if (!node) return;
    setValueNow(measureValueNow(node, orientation));
  });

  // 보조 경로 — 리렌더를 동반하지 않는 외부 변화를 잡는다(예: 창
  // 리사이즈로 부모 컨테이너 크기만 바뀌고 이 컴포넌트의 props/state 는
  // 그대로인 경우). 위 주 경로가 이미 매 렌더 값을 맞추므로, 이 observer 가
  // 침묵하는 환경이어도(관찰 여부는 환경에 따라 다를 수 있다) 드래그로 인한
  // 갱신 자체는 영향받지 않는다.
  useLayoutEffect(() => {
    const node = handleRef.current;
    if (!node) return;

    // ResizeObserver 가 없는 환경(jsdom 등)에서 던지지 않게 가드한다 —
    // window.matchMedia 무가드 호출로 이 브랜치가 한 번 데인 적이 있다
    // (useResizableLayout.ts 참고).
    if (typeof ResizeObserver === "undefined") return;

    const measure = () => setValueNow(measureValueNow(node, orientation));
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
