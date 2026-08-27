"use client";

import { useCallback, useEffect, useMemo, useState, type KeyboardEvent, type UIEvent } from "react";
import { useMedicalSelection } from "@store/medicalSelection";
import { get } from "@/services";
import type { PaginatedResponse } from "@/types/api";
import { Button, EmptyState, Panel, Table } from "@/components/ui";
import styles from "./ViewDataBase.module.css";

type ActiveTab = "disease" | "diagnose";

interface DiseaseItem {
  id: number;
  code: string;
  name: string;
}

interface DiagnoseItem extends DiseaseItem {
  dose: number;
  time: number;
  days: number;
}

type ResultItem = DiseaseItem | DiagnoseItem;

const PAGE_SIZE = 50;

export default function ViewDataBase() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("disease");
  const [diseases, setDiseases] = useState<DiseaseItem[]>([]);
  const [diagnoses, setDiagnoses] = useState<DiagnoseItem[]>([]);
  const [diseaseLoading, setDiseaseLoading] = useState(false);
  const [diagnoseLoading, setDiagnoseLoading] = useState(false);
  const [diseaseAppending, setDiseaseAppending] = useState(false);
  const [diagnoseAppending, setDiagnoseAppending] = useState(false);
  const [diseasePage, setDiseasePage] = useState(-1);
  const [diagnosePage, setDiagnosePage] = useState(-1);
  const [diseaseHasMore, setDiseaseHasMore] = useState(true);
  const [diagnoseHasMore, setDiagnoseHasMore] = useState(true);
  const [errors, setErrors] = useState<Record<ActiveTab, string | null>>({
    disease: null,
    diagnose: null,
  });
  /** 검색 입력창 값 */
  const [searchDraft, setSearchDraft] = useState("");
  /** API에 전달 중인 검색어(검색 버튼·Enter 시 반영) */
  const [appliedSearch, setAppliedSearch] = useState("");
  const { addDisease, addDiagnosis } = useMedicalSelection();

  const fetchDiseases = useCallback(async (pageToLoad = 0) => {
    const isInitialLoad = pageToLoad === 0;
    if (isInitialLoad) {
      setDiseaseLoading(true);
    } else {
      setDiseaseAppending(true);
    }
    setErrors((prev) => ({ ...prev, disease: null }));
    try {
      const q = appliedSearch.trim();
      const response = await get<PaginatedResponse<DiseaseItem>>("/api/diseases", {
        params: {
          page: pageToLoad,
          size: PAGE_SIZE,
          ...(q ? { query: q } : {}),
        },
      });
      setDiseases((prev) => (isInitialLoad ? response.items : [...prev, ...response.items]));
      setDiseasePage(response.page);
      const totalLoaded = response.page * response.pageSize + response.items.length;
      setDiseaseHasMore(totalLoaded < response.total);
    } catch (err) {
      console.error("Failed to load diseases", err);
      setErrors((prev) => ({ ...prev, disease: "상병 정보를 불러오지 못했습니다." }));
    } finally {
      if (isInitialLoad) {
        setDiseaseLoading(false);
      } else {
        setDiseaseAppending(false);
      }
    }
  }, [appliedSearch]);

  const fetchDiagnoses = useCallback(async (pageToLoad = 0) => {
    const isInitialLoad = pageToLoad === 0;
    if (isInitialLoad) {
      setDiagnoseLoading(true);
    } else {
      setDiagnoseAppending(true);
    }
    setErrors((prev) => ({ ...prev, diagnose: null }));
    try {
      const q = appliedSearch.trim();
      const response = await get<PaginatedResponse<DiagnoseItem>>("/api/diagnoses", {
        params: {
          page: pageToLoad,
          size: PAGE_SIZE,
          ...(q ? { query: q } : {}),
        },
      });
      setDiagnoses((prev) => (isInitialLoad ? response.items : [...prev, ...response.items]));
      setDiagnosePage(response.page);
      const totalLoaded = response.page * response.pageSize + response.items.length;
      setDiagnoseHasMore(totalLoaded < response.total);
    } catch (err) {
      console.error("Failed to load diagnoses", err);
      setErrors((prev) => ({ ...prev, diagnose: "처방 정보를 불러오지 못했습니다." }));
    } finally {
      if (isInitialLoad) {
        setDiagnoseLoading(false);
      } else {
        setDiagnoseAppending(false);
      }
    }
  }, [appliedSearch]);

  /** 탭 또는 검색어가 바뀌면 현재 탭 목록을 처음부터 다시 조회 */
  useEffect(() => {
    if (activeTab === "disease") {
      void fetchDiseases(0);
    } else {
      void fetchDiagnoses(0);
    }
  }, [activeTab, appliedSearch, fetchDiseases, fetchDiagnoses]);

  const submitSearch = useCallback(() => {
    setAppliedSearch(searchDraft.trim());
  }, [searchDraft]);

  const handleSearchKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitSearch();
      }
    },
    [submitSearch]
  );

  const itemsToRender = useMemo<ResultItem[]>(() => {
    if (activeTab === "disease") {
      return diseases;
    }
    return diagnoses;
  }, [activeTab, diseases, diagnoses]);

  const isInitialLoading = activeTab === "disease" ? diseaseLoading : diagnoseLoading;
  const isAppendLoading = activeTab === "disease" ? diseaseAppending : diagnoseAppending;
  const activeHasMore = activeTab === "disease" ? diseaseHasMore : diagnoseHasMore;
  const activeError = errors[activeTab];

  const handleTabChange = (tab: ActiveTab) => {
    if (tab !== activeTab) {
      setActiveTab(tab);
    }
  };

  const handleItemDoubleClick = useCallback(
    (item: ResultItem) => {
      if (activeTab === "disease") {
        addDisease(item as DiseaseItem);
      } else {
        const diagnoseItem = item as DiagnoseItem;
        addDiagnosis({
          ...diagnoseItem,
          dose: diagnoseItem.dose ?? 0,
          time: diagnoseItem.time ?? 0,
          days: diagnoseItem.days ?? 0,
        });
      }
    },
    [activeTab, addDisease, addDiagnosis]
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTableRowElement>, item: ResultItem) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handleItemDoubleClick(item);
      }
    },
    [handleItemDoubleClick]
  );

  const handleScroll = useCallback(
    (event: UIEvent<HTMLDivElement>) => {
      const { scrollTop, clientHeight, scrollHeight } = event.currentTarget;
      if (scrollHeight - (scrollTop + clientHeight) > 40) {
        return;
      }

      if (activeTab === "disease") {
        if (!diseaseHasMore || diseaseLoading || diseaseAppending) {
          return;
        }
        void fetchDiseases(diseasePage + 1);
      } else {
        if (!diagnoseHasMore || diagnoseLoading || diagnoseAppending) {
          return;
        }
        void fetchDiagnoses(diagnosePage + 1);
      }
    },
    [
      activeTab,
      diseaseHasMore,
      diagnoseHasMore,
      diseaseLoading,
      diagnoseLoading,
      diseaseAppending,
      diagnoseAppending,
      diseasePage,
      diagnosePage,
      fetchDiseases,
      fetchDiagnoses,
    ]
  );

  return (
    <Panel className={styles.container} title="데이터베이스 조회">
      <div className={styles.searchSection}>
        <input
          type="text"
          placeholder="코드·상병명·처방명 검색 후 Enter 또는 검색"
          className={styles.searchInput}
          disabled={isInitialLoading}
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          onKeyDown={handleSearchKeyDown}
          aria-label="데이터베이스 검색어"
        />
        <Button type="button" variant="secondary" size="sm" disabled={isInitialLoading} onClick={submitSearch}>
          검색
        </Button>
      </div>

      <div className={styles.tabSection}>
        <Button
          type="button"
          variant={activeTab === "disease" ? "secondary" : "ghost"}
          size="sm"
          aria-pressed={activeTab === "disease"}
          onClick={() => handleTabChange("disease")}
          disabled={isInitialLoading && activeTab !== "disease"}
        >
          상병
        </Button>
        <Button
          type="button"
          variant={activeTab === "diagnose" ? "secondary" : "ghost"}
          size="sm"
          aria-pressed={activeTab === "diagnose"}
          onClick={() => handleTabChange("diagnose")}
          disabled={isInitialLoading && activeTab !== "diagnose"}
        >
          처방
        </Button>
      </div>

      <>
        {activeError && itemsToRender.length === 0 ? (
          <EmptyState title={activeError} />
        ) : isInitialLoading && itemsToRender.length === 0 ? (
          <EmptyState title="불러오는 중..." />
        ) : itemsToRender.length === 0 ? (
          <EmptyState title="표시할 데이터가 없습니다." />
        ) : (
          <div className={styles.resultList} onScroll={handleScroll}>
            <Table dense>
              <thead>
                <tr>
                  <th scope="col">코드</th>
                  <th scope="col">명칭</th>
                </tr>
              </thead>
              <tbody>
                {itemsToRender.map((item) => (
                  <tr
                    key={item.id}
                    tabIndex={0}
                    onDoubleClick={() => handleItemDoubleClick(item)}
                    onKeyDown={(event) => handleKeyDown(event, item)}
                    title="더블클릭하거나 Enter 키로 선택 영역에 추가"
                  >
                    <td className={styles.resultCode}>{item.code}</td>
                    <td>{item.name}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            {isAppendLoading ? (
              <p className={styles.appendLoader}>추가 불러오는 중...</p>
            ) : !activeHasMore ? (
              <p className={styles.appendLoader}>마지막 페이지입니다.</p>
            ) : null}
          </div>
        )}
      </>
    </Panel>
  );
}
