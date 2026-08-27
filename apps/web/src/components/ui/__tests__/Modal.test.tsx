import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import Modal from "../Modal";

// jsdom 은 <dialog> 의 모달 동작을 구현하지 않는다. open 속성만 흉내 낸다.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});

describe("Modal", () => {
  it("open=false 면 내용을 표시하지 않는다", () => {
    render(
      <Modal open={false} onClose={() => {}} title="환자 검색">
        본문
      </Modal>
    );
    expect(screen.queryByText("본문")).toBeNull();
  });

  it("open=true 면 dialog 로 렌더하고 title 로 라벨링한다", () => {
    render(
      <Modal open onClose={() => {}} title="환자 검색">
        본문
      </Modal>
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAccessibleName("환자 검색");
    expect(screen.getByText("본문")).toBeInTheDocument();
  });

  it("cancel 이벤트(Escape)에서 onClose 를 호출한다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("닫기 버튼에서 onClose 를 호출한다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
  it("백드롭(다이얼로그 자신) 클릭에서 onClose 를 호출한다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    const dialog = screen.getByRole("dialog");
    // 실제 브라우저 클릭은 같은 대상에서 mousedown -> mouseup -> click 순서로 일어난다.
    fireEvent.mouseDown(dialog);
    fireEvent.mouseUp(dialog);
    fireEvent.click(dialog);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("내용 클릭에서는 onClose 를 호출하지 않는다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    fireEvent.click(screen.getByText("본문"));
    expect(onClose).not.toHaveBeenCalled();
  });

  // 콘텐츠(예: textarea)에서 드래그로 텍스트를 선택하다가 마우스를 백드롭
  // 위에서 놓으면, 브라우저가 만드는 click 이벤트의 target 은 mousedown·
  // mouseup 대상의 공통 조상인 <dialog> 자신이 된다 — 백드롭 클릭과
  // 구분되지 않아 의도치 않게 닫혀버린다(실제 경로: AI 제안 거부로 이어짐).
  it("콘텐츠에서 시작한 드래그가 백드롭에서 끝나도 onClose 를 호출하지 않는다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    fireEvent.mouseDown(screen.getByText("본문"));
    fireEvent.mouseUp(screen.getByRole("dialog"));
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
  });

  // 반대 방향. 백드롭에서 누르고 콘텐츠 위에서 놓아도 click 대상은 <dialog> 가 된다.
  it("백드롭에서 시작한 드래그가 콘텐츠에서 끝나도 onClose 를 호출하지 않는다", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="환자 검색">
        본문
      </Modal>
    );
    fireEvent.mouseDown(screen.getByRole("dialog"));
    fireEvent.mouseUp(screen.getByText("본문"));
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();
  });
});
