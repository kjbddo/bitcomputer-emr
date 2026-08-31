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
