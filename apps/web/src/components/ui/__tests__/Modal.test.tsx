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
});
