"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMedicalSelection } from "@store/medicalSelection";
import { Button, EmptyState, Panel, Table } from "@/components/ui";
import styles from "./Disease.module.css";
import { ClinicVisitContext } from "@/types/clinic";
import { setHistoryDiseases } from "@/services/history";
import { HttpError } from "@/services/http/types";

type DiseaseProps = {
  clinicVisit: ClinicVisitContext | null;
  ensureHistory: () => Promise<number>;
  employeeId: number;
  onHistoryUpdated?: () => void;
};

const DUMMY_DISEASES = [
  { id: 900001, code: "E11", name: "당뇨" },
  { id: 900002, code: "E16.2", name: "저혈당" },
  { id: 900003, code: "E03.9", name: "갑상선 저하증" },
] as const;

export default function Disease({ clinicVisit, ensureHistory, employeeId, onHistoryUpdated }: DiseaseProps) {
  const { diseases, addDisease, removeDisease, clearDiseases } = useMedicalSelection();
  const [saving, setSaving] = useState(false);
  const prevPatientIdRef = useRef<number | null>(null);

  useEffect(() => {
    const currentPatientId = clinicVisit?.patientId ?? null;
    if (prevPatientIdRef.current !== currentPatientId) {
      prevPatientIdRef.current = currentPatientId;
      clearDiseases();
    }
  }, [clinicVisit?.patientId, clearDiseases]);

  const handleSave = useCallback(async () => {
    if (!clinicVisit) {
      alert("환자를 먼저 선택해주세요.");
      return;
    }

    if (diseases.length === 0) {
      return;
    }

    setSaving(true);
    try {
      const historyId = await ensureHistory();
      await setHistoryDiseases(historyId, employeeId, diseases);
      onHistoryUpdated?.();
      alert("상병 정보가 저장되었습니다.");
    } catch (error) {
      console.error("상병 정보 저장 실패:", error);
      if (error instanceof HttpError) {
        alert(`상병 정보를 저장하지 못했습니다. [${error.status}] ${error.message}`);
      } else {
        alert("상병 정보를 저장하지 못했습니다. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setSaving(false);
    }
  }, [clinicVisit, diseases, employeeId, ensureHistory]);

  return (
    <Panel
      className={styles.container}
      title="상병"
      actions={
        <>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleSave}
            disabled={diseases.length === 0 || saving}
            loading={saving}
          >
            저장
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={clearDiseases}
            disabled={diseases.length === 0}
          >
            전체 삭제
          </Button>
        </>
      }
    >
      <div className={styles.quickSelect}>
        <span className={styles.quickSelectLabel}>테스트 상병 빠른 선택</span>
        <div className={styles.quickSelectButtons}>
          {DUMMY_DISEASES.map((disease) => (
            <Button
              key={disease.id}
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => addDisease({ ...disease })}
            >
              {disease.name}
            </Button>
          ))}
        </div>
      </div>
      {diseases.length === 0 ? (
        <EmptyState
          title="선택된 상병이 없습니다."
          description="오른쪽 데이터베이스에서 더블클릭하여 추가하세요."
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <th scope="col">No.</th>
              <th scope="col">ID</th>
              <th scope="col">상병코드</th>
              <th scope="col">상병명칭</th>
              <th scope="col">삭제</th>
            </tr>
          </thead>
          <tbody>
            {diseases.map((item, index) => (
              <tr key={item.id}>
                <td>{index + 1}</td>
                <td>{item.id}</td>
                <td className={styles.code}>{item.code}</td>
                <td>{item.name}</td>
                <td>
                  <Button type="button" variant="danger" size="sm" onClick={() => removeDisease(item.id)}>
                    삭제
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}
