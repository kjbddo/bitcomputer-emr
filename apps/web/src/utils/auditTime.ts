/**
 * 감사 로그 화면(app/(auth)/admin/audit)의 시각 변환 계약.
 *
 * 서버(AuditService.record)는 `LocalDateTime.now()`를 occurred_at 컬럼에 그대로
 * 저장한다 - 시간대 정보가 없는 "UTC-naive" 값이고, 배포 JVM 의 기본 시간대가
 * UTC 라 실제로는 UTC 시각의 벽시계 값이 문자열로 온다(예: "2026-08-28T01:11:49").
 * DB 컬럼 자체에는 시간대 표시가 없으므로, 이 문자열을 UTC 로 해석하는 것은
 * 서버가 아니라 클라이언트의 책임이다 - 그 계약을 이 파일에 모아 둔다.
 *
 * - 서버 -> 화면 표시: parseOccurredAtUtc 로 UTC 로 해석한 뒤, 뷰어의 로컬
 *   시간대로 포맷한다(formatLocalTimestamp).
 * - 화면의 로컬 날짜 필터 -> 서버 파라미터: 뷰어가 고른 캘린더 날짜의 자정/23:59:59
 *   경계를 로컬 시간대 기준으로 잡은 뒤, 서버가 저장하는 것과 같은 형식(UTC
 *   벽시계, "yyyy-MM-ddTHH:mm:ss")으로 변환해 보낸다(localDayStartToUtcParam /
 *   localDayEndToUtcParam). 그러지 않으면 "오늘" 필터가 실제로는 UTC 00:00-23:59
 *   를 조회해, KST 기준 오늘 00:00-09:00 이 빠지고 어제 09:00-24:00 이 섞여 들어간다.
 *
 * 아래 함수들은 모두 시간대를 분(minute) 오프셋으로 명시적으로 받는다(기본값은
 * 실행 환경의 로컬 오프셋). 이 덕분에 순수 함수로 테스트할 수 있다 - 테스트
 * 환경의 실제 시스템 시간대(ambient TZ)에 기대지 않고 원하는 오프셋을 직접
 * 주입해 검증한다.
 */

/** UTC 오프셋(분). 양수면 UTC 보다 빠르다(KST = +540). 기본값은 실행 환경의 로컬 시간대. */
function defaultOffsetMinutes(): number {
  // Date.prototype.getTimezoneOffset() 은 부호가 반대다(로컬이 UTC 보다 느리면 양수).
  return -new Date().getTimezoneOffset();
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** 서버가 내려준 UTC-naive LocalDateTime 문자열을 실제 UTC 시각으로 해석한다. */
export function parseOccurredAtUtc(occurredAt: string): Date {
  return new Date(`${occurredAt}Z`);
}

/**
 * occurredAt 을 지정한 시간대(분 오프셋)의 벽시계 문자열로 포맷한다.
 * 시스템 Date 의 로컬 getter 를 쓰지 않고 epoch ms 를 직접 이동시킨 뒤
 * getUTC* 로 읽는다 - 그래서 실행 환경의 실제 시간대와 무관하게 결정적이다.
 */
export function formatLocalTimestamp(
  occurredAt: string,
  offsetMinutes: number = defaultOffsetMinutes()
): string {
  const shifted = new Date(parseOccurredAtUtc(occurredAt).getTime() + offsetMinutes * 60000);
  return (
    `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())} ` +
    `${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}:${pad(shifted.getUTCSeconds())}`
  );
}

function localWallClockToUtcParam(
  dateStr: string,
  hh: number,
  mm: number,
  ss: number,
  offsetMinutes: number
): string {
  const [y, mo, d] = dateStr.split("-").map(Number);
  // dateStr+시각을 "로컬 벽시계"로 두고, UTC 기준값(Date.UTC)으로 임시 표현한 뒤
  // 시간대 오프셋만큼 빼서 진짜 UTC epoch ms 를 구한다. 그 값을 다시 getUTC* 로
  // 읽으면 로컬 시각의 UTC 등가 벽시계 문자열이 나온다.
  const localAsUtcMs = Date.UTC(y, mo - 1, d, hh, mm, ss);
  const trueUtcMs = localAsUtcMs - offsetMinutes * 60000;
  const u = new Date(trueUtcMs);
  return (
    `${u.getUTCFullYear()}-${pad(u.getUTCMonth() + 1)}-${pad(u.getUTCDate())}T` +
    `${pad(u.getUTCHours())}:${pad(u.getUTCMinutes())}:${pad(u.getUTCSeconds())}`
  );
}

/** 로컬 캘린더 날짜(yyyy-MM-dd)의 00:00:00 을 서버 필터 파라미터용 UTC 문자열로. */
export function localDayStartToUtcParam(
  dateStr: string,
  offsetMinutes: number = defaultOffsetMinutes()
): string {
  return localWallClockToUtcParam(dateStr, 0, 0, 0, offsetMinutes);
}

/** 로컬 캘린더 날짜(yyyy-MM-dd)의 23:59:59 를 서버 필터 파라미터용 UTC 문자열로. */
export function localDayEndToUtcParam(
  dateStr: string,
  offsetMinutes: number = defaultOffsetMinutes()
): string {
  return localWallClockToUtcParam(dateStr, 23, 59, 59, offsetMinutes);
}
