"use client";

import { useState } from "react";
import { Button } from "@/components/ui";
import styles from "./ActionBar.module.css";
import SearchPatientModal from "./SearchPatientModal";
import { PatientInfo } from "./PatientInfoBar";

type ActionBarProps = {
  onPatientSelect: (patient: PatientInfo, visit?: unknown) => void;
  onRegisterClick?: () => void;
  isRegisterPrimary?: boolean;
};

export default function ActionBar({ onPatientSelect, onRegisterClick, isRegisterPrimary = false }: ActionBarProps) {
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);

  const today = new Date().toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  const handleSearchClick = () => {
    setIsSearchModalOpen(true);
  };

  const closeSearchModal = () => {
    setIsSearchModalOpen(false);
  };

  return (
    <>
      <div className={styles.actionBar}>
        <div className={styles.leftSection}>
          <span className={styles.date}>{today}</span>
        </div>

        <div className={styles.rightSection}>
          <Button
            type="button"
            variant={isRegisterPrimary ? "primary" : "secondary"}
            onClick={onRegisterClick}
          >
            환자 등록
          </Button>
          <Button type="button" variant="secondary" onClick={handleSearchClick}>
            환자 조회
          </Button>
        </div>
      </div>

      <SearchPatientModal
        open={isSearchModalOpen}
        onClose={closeSearchModal}
        title="환자 조회"
        onSelectPatient={(patient) => {
          onPatientSelect(patient);
        }}
      />
    </>
  );
}
