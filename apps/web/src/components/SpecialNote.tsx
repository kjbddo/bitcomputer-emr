"use client";

import { EmptyState, Panel } from "@/components/ui";
import styles from "./SpecialNote.module.css";

export default function SpecialNote() {
  const specialNotes = [
    "특이사항 없음."
  ];

  return (
    <Panel className={styles.container} title="특이사항">
      {specialNotes.length === 0 ? (
        <EmptyState title="등록된 특이사항이 없습니다" />
      ) : (
        <div className={styles.notesList}>
          {specialNotes.map((note, index) => (
            <div key={index} className={styles.noteItem}>
              {note}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
