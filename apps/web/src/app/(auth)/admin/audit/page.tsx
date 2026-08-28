"use client";

import { useEffect, useState } from "react";
import { getAuditLogs } from "@/services/admin";
import { AuditFilter, AuditLog, Page } from "@/types/audit";
import { Badge, Button, EmptyState, Field, Panel, Table } from "@/components/ui";
import styles from "./page.module.css";

const PAGE_SIZE = 50;

type DraftFilter = {
  actorUsername: string;
  targetPatientId: string;
  action: string;
  outcome: string;
  from: string;
  to: string;
};

const EMPTY_DRAFT: DraftFilter = {
  actorUsername: "",
  targetPatientId: "",
  action: "",
  outcome: "",
  from: "",
  to: "",
};

type AppliedFilter = Omit<AuditFilter, "page" | "size">;

// 백엔드에 실제로 존재하는 outcome 값은 GRANTED / DENIED 둘뿐이다(자유
// 문자열 컬럼이라 그 외 값이 들어올 가능성은 남아 있어 badgeTone 은
// 알 수 없는 값을 neutral 로 떨어뜨린다).
function outcomeTone(outcome: string): "danger" | "success" | "neutral" {
  if (outcome === "DENIED") return "danger";
  if (outcome === "GRANTED") return "success";
  return "neutral";
}

function toAppliedFilter(draft: DraftFilter): AppliedFilter {
  const filter: AppliedFilter = {};

  const actor = draft.actorUsername.trim();
  if (actor) filter.actorUsername = actor;

  // 빈 입력은 파라미터 자체를 보내지 않아야 한다 - 0 이나 NaN 을 보내면
  // getAuditLogs 가 0 은 그대로 유지하므로 의도치 않게 환자 ID=0 필터가
  // 걸린다.
  const patientId = draft.targetPatientId.trim();
  if (patientId !== "") {
    const parsed = Number(patientId);
    if (Number.isFinite(parsed)) filter.targetPatientId = parsed;
  }

  const action = draft.action.trim();
  if (action) filter.action = action;

  if (draft.outcome) filter.outcome = draft.outcome;
  if (draft.from) filter.from = `${draft.from}T00:00:00`;
  if (draft.to) filter.to = `${draft.to}T23:59:59`;

  return filter;
}

function formatTimestamp(occurredAt: string): string {
  return occurredAt.replace("T", " ").slice(0, 19);
}

export default function AuditPage() {
  const [draft, setDraft] = useState<DraftFilter>(EMPTY_DRAFT);
  const [appliedFilter, setAppliedFilter] = useState<AppliedFilter>({});
  const [page, setPage] = useState(0);

  const [result, setResult] = useState<Page<AuditLog> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    load(0, {});
  }, []);

  async function load(targetPage: number, filter: AppliedFilter) {
    setLoading(true);
    setError(null);
    try {
      const data = await getAuditLogs({ ...filter, page: targetPage, size: PAGE_SIZE });
      setResult(data);
      setPage(targetPage);
    } catch (err) {
      setError(err instanceof Error ? err.message : "감사 로그를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }

  function updateDraft<K extends keyof DraftFilter>(key: K, value: string) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const filter = toAppliedFilter(draft);
    setAppliedFilter(filter);
    await load(0, filter);
  }

  function handlePrev() {
    if (page <= 0) return;
    load(page - 1, appliedFilter);
  }

  function handleNext() {
    if (!result || page >= result.totalPages - 1) return;
    load(page + 1, appliedFilter);
  }

  function handleRetry() {
    load(page, appliedFilter);
  }

  return (
    <div className={styles.container}>
      <div className={styles.wrapper}>
        <Panel title="감사 로그 필터">
          <form className={styles.filters} onSubmit={handleSearch}>
            <div className={styles.filterField}>
              <Field label="행위자" htmlFor="audit-actor" hint="부분 일치">
                <input
                  id="audit-actor"
                  value={draft.actorUsername}
                  onChange={(e) => updateDraft("actorUsername", e.target.value)}
                  placeholder="계정 일부"
                />
              </Field>
            </div>
            <div className={styles.filterField}>
              <Field label="환자 ID" htmlFor="audit-patient">
                <input
                  id="audit-patient"
                  value={draft.targetPatientId}
                  onChange={(e) => updateDraft("targetPatientId", e.target.value)}
                  inputMode="numeric"
                />
              </Field>
            </div>
            <div className={styles.filterField}>
              <Field label="행위" htmlFor="audit-action">
                <input
                  id="audit-action"
                  value={draft.action}
                  onChange={(e) => updateDraft("action", e.target.value)}
                  placeholder="PATIENT_VIEW"
                />
              </Field>
            </div>
            <div className={styles.filterField}>
              <Field label="결과" htmlFor="audit-outcome">
                <select
                  id="audit-outcome"
                  value={draft.outcome}
                  onChange={(e) => updateDraft("outcome", e.target.value)}
                >
                  <option value="">전체</option>
                  <option value="GRANTED">허용</option>
                  <option value="DENIED">거부</option>
                </select>
              </Field>
            </div>
            <div className={styles.filterField}>
              <Field label="시작일" htmlFor="audit-from">
                <input
                  id="audit-from"
                  type="date"
                  value={draft.from}
                  onChange={(e) => updateDraft("from", e.target.value)}
                />
              </Field>
            </div>
            <div className={styles.filterField}>
              <Field label="종료일" htmlFor="audit-to">
                <input
                  id="audit-to"
                  type="date"
                  value={draft.to}
                  onChange={(e) => updateDraft("to", e.target.value)}
                />
              </Field>
            </div>
            <Button type="submit" variant="primary" disabled={loading} loading={loading}>
              조회
            </Button>
          </form>
        </Panel>

        <Panel title="감사 로그 목록" padding="none">
          {loading ? (
            <EmptyState title="불러오는 중..." />
          ) : error ? (
            <EmptyState
              title="감사 로그를 불러오지 못했습니다"
              description={error}
              action={
                <Button variant="secondary" size="sm" onClick={handleRetry}>
                  다시 시도
                </Button>
              }
            />
          ) : !result || result.content.length === 0 ? (
            <EmptyState title="조건에 맞는 기록이 없습니다" />
          ) : (
            <>
              <Table aria-label="감사 로그 목록" stickyHeader maxHeight="60vh">
                <thead>
                  <tr>
                    <th scope="col">시각</th>
                    <th scope="col">행위자</th>
                    <th scope="col">역할</th>
                    <th scope="col">행위</th>
                    <th scope="col">환자</th>
                    <th scope="col">결과</th>
                    <th scope="col">IP</th>
                    <th scope="col">상세</th>
                  </tr>
                </thead>
                <tbody>
                  {result.content.map((log) => (
                    <tr key={log.id} className={log.outcome === "DENIED" ? styles.denied : undefined}>
                      <td>{formatTimestamp(log.occurredAt)}</td>
                      <td>{log.actorUsername}</td>
                      <td>{log.actorRole}</td>
                      <td>{log.action}</td>
                      <td>{log.targetPatientId ?? "-"}</td>
                      <td>
                        <Badge tone={outcomeTone(log.outcome)}>{log.outcome}</Badge>
                      </td>
                      <td>{log.requestIp ?? "-"}</td>
                      <td className={styles.detail}>{log.detail ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>

              <div className={styles.pager}>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handlePrev}
                  disabled={loading || page <= 0}
                >
                  이전
                </Button>
                <p className={styles.pagerStatus} role="status">
                  {page + 1} / {Math.max(result.totalPages, 1)} 페이지 (총 {result.totalElements}건)
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleNext}
                  disabled={loading || page >= result.totalPages - 1}
                >
                  다음
                </Button>
              </div>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}
