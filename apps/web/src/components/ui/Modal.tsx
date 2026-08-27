"use client";

import { useEffect, useRef } from "react";

import Button from "./Button";
import styles from "./Modal.module.css";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
}

export default function Modal({ open, onClose, title, footer, size = "md", children }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const mouseDownOnBackdropRef = useRef(false);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      // showModal 이 포커스 트랩·Escape·top-layer 를 담당한다.
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const handleCancel = (event: Event) => {
      event.preventDefault();
      onClose();
    };
    dialog.addEventListener("cancel", handleCancel);
    return () => dialog.removeEventListener("cancel", handleCancel);
  }, [onClose]);

  /**
   * 백드롭 클릭으로 닫기.
   *
   * <dialog> 의 패딩이 0 이라 다이얼로그 요소 자신이 이벤트 대상이 되는 경우는
   * 백드롭을 눌렀을 때뿐이다. 내용은 전부 자식 요소 안에 있으므로 내용 클릭은
   * 여기 걸리지 않는다. 이관 전 자체 구현 오버레이들이 갖고 있던 동작이다.
   *
   * 다만 click 이벤트 하나만으로는 부족하다: 콘텐츠 안(예: textarea, input)에서
   * 마우스를 눌러 드래그로 텍스트를 선택하다가 백드롭 위에서 버튼을 놓으면,
   * mousedown 대상과 mouseup 대상이 갈라져 브라우저가 만드는 click 이벤트의
   * target 은 둘의 공통 조상인 <dialog> 자신이 된다 — 즉 콘텐츠 안에서 시작한
   * 드래그인데도 "백드롭 클릭"과 구분되지 않는다. mousedown 이 실제로 백드롭
   * 자신에서 시작했을 때만 닫히도록, mousedown 대상도 함께 확인한다.
   */
  const handleBackdropMouseDown = (event: React.MouseEvent<HTMLDialogElement>) => {
    mouseDownOnBackdropRef.current = event.target === ref.current;
  };

  const handleBackdropClick = (event: React.MouseEvent<HTMLDialogElement>) => {
    const startedOnBackdrop = mouseDownOnBackdropRef.current;
    mouseDownOnBackdropRef.current = false;
    if (event.target === ref.current && startedOnBackdrop) {
      onClose();
    }
  };

  return (
    <dialog
      ref={ref}
      className={`${styles.dialog} ${styles[size]}`}
      aria-label={title}
      onMouseDown={handleBackdropMouseDown}
      onClick={handleBackdropClick}
    >
      {open && (
        <>
          <div className={styles.header}>
            <h2 className={styles.title}>{title}</h2>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="닫기">
              ✕
            </Button>
          </div>
          <div className={styles.body}>{children}</div>
          {footer && <div className={styles.footer}>{footer}</div>}
        </>
      )}
    </dialog>
  );
}
