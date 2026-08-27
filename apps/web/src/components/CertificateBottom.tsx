"use client";

import { useEffect, useMemo, useState } from "react";
import styles from "./CertificateBottom.module.css";
import { Button, EmptyState, Panel, Table, rowActivateProps } from "@/components/ui";
import { getPatientHistories, getHistoryDiseases, type HistoryDiseaseResponse } from "@services/history";

const TABS = ["상병", "상용구", "과거처방", "사용자설정"] as const;
type Tab = typeof TABS[number];

interface HistoryVisitGroup {
  historyId: number;
  entryDate: string;
  diseases: HistoryDiseaseResponse[];
}

export interface CertificateDiseaseApplyPayload {
  diseaseCode: string;
  primaryDiseaseName: string;
  additionalDiseaseNames: string;
  historyId: number;
}

function buildDiseaseApplyPayload(
  diseases: HistoryDiseaseResponse[],
  historyId: number
): CertificateDiseaseApplyPayload {
  return {
    diseaseCode: diseases
      .map((d) => d.code.trim())
      .filter(Boolean)
      .join("\n"),
    primaryDiseaseName: diseases[0]?.name.trim() ?? "",
    additionalDiseaseNames: diseases
      .slice(1)
      .map((d) => d.name.trim())
      .filter(Boolean)
      .join("\n"),
    historyId,
  };
}

interface Props {
  patientId?: number;
  employeeId: number;
  onApplyDiagnosisToCertificate?: (payload: CertificateDiseaseApplyPayload) => void;
}

export default function CertificateBottom({
  patientId,
  employeeId,
  onApplyDiagnosisToCertificate,
}: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("상병");
  const [visitGroups, setVisitGroups] = useState<HistoryVisitGroup[]>([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!patientId) {
      setVisitGroups([]);
      setSelectedHistoryId(null);
      return;
    }

    let cancelled = false;

    const fetchDiseases = async () => {
      setLoading(true);
      setError(null);
      try {
        const { histories } = await getPatientHistories(employeeId, patientId);

        const results = await Promise.allSettled(
          histories.map((h) =>
            getHistoryDiseases(h.id, employeeId).then((list) => ({
              historyId: h.id,
              entryDate: h.entryDate,
              diseases: list,
            }))
          )
        );

        if (cancelled) return;

        const groups: HistoryVisitGroup[] = histories.map((h, i) => {
          const r = results[i];
          if (r.status === "fulfilled") return r.value;
          return { historyId: h.id, entryDate: h.entryDate, diseases: [] };
        });

        groups.sort((a, b) => b.entryDate.localeCompare(a.entryDate));

        setVisitGroups(groups);
        setSelectedHistoryId(groups[0]?.historyId ?? null);
      } catch {
        if (!cancelled) {
          setError("상병 내역을 불러오지 못했습니다.");
          setVisitGroups([]);
          setSelectedHistoryId(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchDiseases();
    return () => { cancelled = true; };
  }, [patientId, employeeId]);

  const selectedDiseases = useMemo(() => {
    if (selectedHistoryId == null) return [];
    const g = visitGroups.find((v) => v.historyId === selectedHistoryId);
    return g?.diseases ?? [];
  }, [visitGroups, selectedHistoryId]);

  return (
    <Panel className={styles.container} padding="none">
      <div className={styles.tabBar}>
        {TABS.map((tab) => (
          <Button
            key={tab}
            type="button"
            variant={activeTab === tab ? "secondary" : "ghost"}
            size="sm"
            className={styles.tab}
            aria-pressed={activeTab === tab}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </Button>
        ))}
      </div>

      <div className={styles.body}>
        {activeTab === "상병" && (
          <>
            {loading && <EmptyState title="조회 중..." />}
            {!loading && error && <EmptyState title={error} />}
            {!loading && !error && !patientId && (
              <EmptyState title="환자를 조회하면 진료별 상병이 표시됩니다." />
            )}
            {!loading && !error && patientId && visitGroups.length === 0 && (
              <EmptyState title="진료 이력이 없습니다." />
            )}
            {!loading && !error && patientId && visitGroups.length > 0 && (
              <div className={styles.diseaseSplit}>
                <div className={styles.historyColumn}>
                  <div className={styles.columnTitle}>진료일 (이력)</div>
                  <div className={styles.historyTableWrap}>
                    <Table dense aria-label="진료 이력">
                      <thead>
                        <tr>
                          <th scope="col">진료일</th>
                          <th scope="col">상병</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visitGroups.map((g) => (
                          <tr
                            key={g.historyId}
                            aria-current={g.historyId === selectedHistoryId || undefined}
                            onClick={() => setSelectedHistoryId(g.historyId)}
                            {...rowActivateProps(() => setSelectedHistoryId(g.historyId))}
                          >
                            <td>{g.entryDate.slice(0, 10)}</td>
                            <td>{g.diseases.length}건</td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </div>
                <div className={styles.diseaseColumn}>
                  <div className={styles.diseaseHeaderRow}>
                    <div className={styles.columnTitle}>해당 진료 상병</div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={selectedDiseases.length === 0 || !onApplyDiagnosisToCertificate}
                      onClick={() => {
                        if (
                          selectedDiseases.length > 0 &&
                          selectedHistoryId != null &&
                          onApplyDiagnosisToCertificate
                        ) {
                          onApplyDiagnosisToCertificate(
                            buildDiseaseApplyPayload(selectedDiseases, selectedHistoryId)
                          );
                        }
                      }}
                    >
                      적용
                    </Button>
                  </div>
                  {selectedDiseases.length === 0 ? (
                    <EmptyState title="이 진료에 등록된 상병이 없습니다." />
                  ) : (
                    <div className={styles.diseaseTableWrap}>
                      <Table dense>
                        <thead>
                          <tr>
                            <th scope="col">No.</th>
                            <th scope="col">상병코드</th>
                            <th scope="col">상병명</th>
                            <th scope="col">구분</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedDiseases.map((d, i) => (
                            <tr key={d.id}>
                              <td>{i + 1}</td>
                              <td>{d.code}</td>
                              <td>{d.name}</td>
                              <td>{d.degree ?? "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
        {activeTab === "상용구" && <EmptyState title="상용구 내용을 여기에 추가하세요." />}
        {activeTab === "과거처방" && <EmptyState title="과거처방 내용을 여기에 추가하세요." />}
        {activeTab === "사용자설정" && <EmptyState title="사용자설정 내용을 여기에 추가하세요." />}
      </div>
    </Panel>
  );
}
