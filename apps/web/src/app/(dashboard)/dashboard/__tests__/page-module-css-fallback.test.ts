import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * C1/C2 회귀 가드.
 *
 * page.tsx 는 layout.enabled 일 때만(뷰포트 1025px 이상, 하이드레이션 후,
 * matchMedia 존재) ResizeHandle 을 그리드 자식으로 렌더한다. 비활성 상태에서는
 * 그리드 자식이 패널 N 개뿐인데, page.module.css 의 `var(--col-tracks, ...)` /
 * `var(--row-tracks, ...)` 폴백값이 핸들 트랙을 포함한 2N-1 개 모양이면 CSS 그리드
 * 자동 배치가 마지막 패널(들)을 핸들 몫 6px 트랙에 욱여넣는다 — 화면에서는 패널이
 * 6px 로 찌부러지는 것으로 보인다(브라우저 실측으로 확인된 회귀, C1/C2).
 *
 * jsdom 에는 레이아웃 엔진이 없어 픽셀을 잴 수는 없지만, "비활성 상태의 그리드
 * 자식 수 == CSS 폴백 트랙 수" 라는 불변식은 CSS 원문을 정적으로 읽어 검사할 수
 * 있다. 트랙 수는 각 그리드가 실제로 갖는 패널 수로 하드코딩해 둔다 — page.tsx 의
 * 패널 구성이 바뀌면(패널 추가/삭제) 이 값도 함께 갱신해야 한다.
 */

const CSS_PATH = resolve(__dirname, "../page.module.css");

/** CSS 원문에서 `.className { ... }` 의 첫 번째(= 미디어쿼리 밖, 기본) 규칙 본문을 돌려준다. */
function firstRuleBody(css: string, className: string): string {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`\\.${escaped}\\s*\\{([^}]*)\\}`));
  if (!match) {
    throw new Error(`.${className} 규칙을 page.module.css 에서 찾지 못했다`);
  }
  return match[1];
}

/** `var(--col-tracks, 300px 1fr 1fr)` 같은 선언에서 폴백 트랙 개수를 센다. */
function fallbackTrackCount(ruleBody: string, axis: "col" | "row"): number {
  const match = ruleBody.match(new RegExp(`var\\(--${axis}-tracks,\\s*([^)]+)\\)`));
  if (!match) {
    throw new Error(`--${axis}-tracks 폴백을 규칙 본문에서 찾지 못했다: ${ruleBody}`);
  }
  return match[1].trim().split(/\s+/).length;
}

// className -> [축, 기대 트랙 수(= 그 그리드의 실제 패널 수)]
// page.tsx 의 렌더 구조와 대응한다:
//   .contentGrid            환자접수 3열 (left/middle/right)
//   .contentGridClinic      진료실 3열 (left/middle/right)
//   .contentGridCertificate 진단서 3열 (left/center/right)
//   .leftColumn             환자접수 왼쪽 열 2행 (SpecialNote/History)
//   .rightColumn            환자접수 오른쪽 열 2행 (WaitingStatus/MedicalInfo)
//   .clinicMiddleColumn     진료실 가운데 열 3행 (WaitingStatus/Disease/Diagnosis)
//   .clinicRightColumn      진료실 오른쪽 열 2행 (ViewDataBase/AIReport)
//   .certificateCenterColumn 진단서 가운데 열 2행 (CertificateList/CertificateBottom)
const EXPECTATIONS: Array<{ className: string; axis: "col" | "row"; expectedTracks: number }> = [
  { className: "contentGrid", axis: "col", expectedTracks: 3 },
  { className: "contentGridClinic", axis: "col", expectedTracks: 3 },
  { className: "contentGridCertificate", axis: "col", expectedTracks: 3 },
  { className: "leftColumn", axis: "row", expectedTracks: 2 },
  { className: "rightColumn", axis: "row", expectedTracks: 2 },
  { className: "clinicMiddleColumn", axis: "row", expectedTracks: 3 },
  { className: "clinicRightColumn", axis: "row", expectedTracks: 2 },
  { className: "certificateCenterColumn", axis: "row", expectedTracks: 2 },
];

describe("page.module.css 폴백 트랙 수 가드 (C1/C2)", () => {
  const css = readFileSync(CSS_PATH, "utf8");

  it.each(EXPECTATIONS)(
    ".$className 의 $axis-tracks 폴백은 핸들 트랙 없이 패널 수($expectedTracks)만큼이어야 한다",
    ({ className, axis, expectedTracks }) => {
      const body = firstRuleBody(css, className);
      expect(fallbackTrackCount(body, axis)).toBe(expectedTracks);
    }
  );
});
