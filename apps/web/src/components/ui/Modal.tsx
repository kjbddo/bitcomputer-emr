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

  return (
    <dialog ref={ref} className={`${styles.dialog} ${styles[size]}`} aria-label={title}>
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
