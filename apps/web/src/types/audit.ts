export interface AuditLog {
  id: number;
  occurredAt: string;
  actorUsername: string;
  actorRole: string;
  action: string;
  targetPatientId: number | null;
  targetHistoryId: number | null;
  requestIp: string | null;
  outcome: string;
  detail: string | null;
}

export interface AuditFilter {
  actorUsername?: string;
  targetPatientId?: number;
  action?: string;
  outcome?: string;
  from?: string;
  to?: string;
  page?: number;
  size?: number;
}

/** Spring Data 의 Page 응답 중 화면이 쓰는 필드만. */
export interface Page<T> {
  content: T[];
  totalElements: number;
  totalPages: number;
  number: number;
  size: number;
}
