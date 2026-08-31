import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

/**
 * jsdom 은 레이아웃이 없어 `getBoundingClientRect` 가 항상 0을 준다.
 * 요소의 `data-stub-width`/`data-stub-height` 속성값을 그대로
 * width/height 로 돌려주는 스텁으로 대체한다 — 속성이 없으면 0.
 */
function stubBoundingClientRect() {
  return vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
    this: HTMLElement
  ) {
    const width = Number(this.dataset.stubWidth ?? 0);
    const height = Number(this.dataset.stubHeight ?? 0);
    return {
      width,
      height,
      top: 0,
      left: 0,
      right: width,
      bottom: height,
      x: 0,
      y: 0,
      toJSON() {
        return {};
      },
    } as DOMRect;
  });
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  callback: ResizeObserverCallback;
  observedElements: Element[] = [];
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    FakeResizeObserver.instances.push(this);
  }
  observe(el: Element) {
    this.observedElements.push(el);
  }
  unobserve() {}
  disconnect() {}
  trigger() {
    this.callback([], this as unknown as ResizeObserver);
  }
}

function setupWithSibling(
  orientation: "vertical" | "horizontal",
  parentSize: number,
  siblingSize: number
) {
  const onDelta = vi.fn();
  const dim = orientation === "vertical" ? "Width" : "Height";
  const parentProps = { [`data-stub-${dim.toLowerCase()}`]: String(parentSize) };
  const siblingProps = { [`data-stub-${dim.toLowerCase()}`]: String(siblingSize) };
  const { container } = render(
    <div {...parentProps}>
      <div data-testid="sibling" {...siblingProps} />
      <ResizeHandle orientation={orientation} label="왼쪽 열 너비 조절" onDelta={onDelta} />
    </div>
  );
  const handle = screen.getByRole("separator", { name: "왼쪽 열 너비 조절" });
  (handle as HTMLElement).setPointerCapture = vi.fn();
  (handle as HTMLElement).releasePointerCapture = vi.fn();
  const sibling = screen.getByTestId("sibling");
  return { handle, sibling, onDelta, container };
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

  it("가로 핸들은 세로 이동량을 쓴다", () => {
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

  it("다른 포인터가 누르지 않고 움직이면 무시한다", () => {
    const { handle, onDelta } = setup();
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 100 });
    onDelta.mockClear();
    fireEvent.pointerMove(handle, { pointerId: 2, clientX: 140 });
    expect(onDelta).not.toHaveBeenCalled();
  });

  it("다른 포인터가 떼어도 드래그 중인 포인터는 계속 반응한다", () => {
    const { handle, onDelta } = setup();
    fireEvent.pointerDown(handle, { pointerId: 1, clientX: 100 });
    fireEvent.pointerUp(handle, { pointerId: 2, clientX: 100 });
    onDelta.mockClear();
    fireEvent.pointerMove(handle, { pointerId: 1, clientX: 140 });
    expect(onDelta).toHaveBeenCalledWith(40);
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

  it("가로 핸들은 위아래 화살표를 쓴다", () => {
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

describe("aria-valuenow", () => {
  let rectSpy: ReturnType<typeof stubBoundingClientRect>;

  beforeEach(() => {
    rectSpy = stubBoundingClientRect();
  });

  afterEach(() => {
    rectSpy.mockRestore();
    FakeResizeObserver.instances = [];
  });

  it("aria-valuemin/max 를 0/100 으로 노출한다", () => {
    const { handle } = setupWithSibling("vertical", 800, 200);
    expect(handle).toHaveAttribute("aria-valuemin", "0");
    expect(handle).toHaveAttribute("aria-valuemax", "100");
  });

  it("마운트 시 앞 형제 폭 / 부모 폭 을 백분율로 동기 보고한다 (vertical)", () => {
    const { handle } = setupWithSibling("vertical", 800, 200);
    expect(handle).toHaveAttribute("aria-valuenow", "25");
  });

  it("horizontal 은 높이를 기준으로 계산한다", () => {
    const { handle } = setupWithSibling("horizontal", 600, 120);
    expect(handle).toHaveAttribute("aria-valuenow", "20");
  });

  it("앞 형제가 없으면 aria-valuenow 를 생략한다", () => {
    const { handle } = setup("vertical");
    expect(handle).not.toHaveAttribute("aria-valuenow");
  });

  it("부모 크기가 0이면 aria-valuenow 를 생략한다", () => {
    const { handle } = setupWithSibling("vertical", 0, 200);
    expect(handle).not.toHaveAttribute("aria-valuenow");
  });

  it("ResizeObserver 가 없는 환경에서도 렌더가 죽지 않는다", () => {
    const original = window.ResizeObserver;
    // @ts-expect-error jsdom 등 구현이 없는 환경을 흉내낸다.
    delete window.ResizeObserver;
    expect(() => setupWithSibling("vertical", 800, 200)).not.toThrow();
    window.ResizeObserver = original;
  });

  it("ResizeObserver 콜백으로 드래그 이후 크기 변화를 따라간다", () => {
    // 테스트 전용 가짜 구현체를 주입한다. FakeResizeObserver 는
    // ResizeObserver 인터페이스를 구조적으로 만족해 타입 단언이 필요 없다.
    window.ResizeObserver = FakeResizeObserver;
    const { handle, sibling } = setupWithSibling("vertical", 800, 200);
    expect(handle).toHaveAttribute("aria-valuenow", "25");

    sibling.setAttribute("data-stub-width", "400");
    act(() => {
      FakeResizeObserver.instances.forEach((observer) => observer.trigger());
    });

    expect(handle).toHaveAttribute("aria-valuenow", "50");
  });
});
