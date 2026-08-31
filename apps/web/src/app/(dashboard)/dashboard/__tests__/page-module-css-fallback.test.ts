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

/**
 * 단일 패널 열(`.middleColumn`, `.certificateRightColumn`) 가드.
 *
 * 위 C1/C2 가드는 "핸들 렌더 시 그리드 자식 수 == 폴백 트랙 수"를 정확한
 * 개수 일치로 검사한다. 단일 패널 열은 다른 메커니즘을 쓴다 — 트랙이
 * 항상 정확히 둘(패널 트랙 + 핸들 트랙)이고, 둘째 트랙이 `auto` 라
 * 핸들이 없으면(비활성 상태) 콘텐츠 크기 0으로 저절로 접힌다. 그래서
 * "개수 일치"가 아니라 "둘째 트랙이 반드시 `auto` 여야 한다"가 이
 * 열들의 불변식이다 — 누군가 이 열도 다른 열처럼 `HANDLE_TRACK_PX`
 * 하드코딩(예: `var(--panel-track, 1fr) 6px`)으로 "맞춰" 버리면, 비활성
 * 상태에서 그리드 자식은 패널 하나뿐인데 트랙은 여전히 둘이라 자동
 * 배치가 패널을 첫 트랙에만 욱여넣고 둘째 트랙(6px)이 빈 채로 남아
 * 패널이 열 높이의 일부만 채우는 회귀가 재현된다 — C1/C2 와 같은 부류의
 * 버그다. 이 가드는 그 회귀를 정적으로 막는다.
 */
describe("page.module.css 단일 패널 열 트랙 가드", () => {
  const css = readFileSync(CSS_PATH, "utf8");

  it.each(["middleColumn", "certificateRightColumn"])(
    ".%s 는 grid-template-rows: var(--panel-track, 1fr) auto 여야 한다 — 둘째 트랙이 auto 가 아니면 비활성 상태에서 패널이 찌부러진다",
    (className) => {
      const body = firstRuleBody(css, className);
      const match = body.match(/grid-template-rows:\s*([^;]+);/);
      expect(match).not.toBeNull();
      expect(match?.[1].trim()).toBe("var(--panel-track, 1fr) auto");
    }
  );

  // 브라우저 실측(대시보드)으로 확인된 회귀 두 건에 대한 정적 가드.
  //
  // 1) gap — 기본 규칙은 gap:0 이어야 한다. row-gap 은 그리드에 트랙이
  //    몇 개 있는지로 몫을 매기지, 그 트랙에 실제 항목이 들어있는지는
  //    보지 않는다. `:only-child` 로 "자식이 하나뿐이면 0" 을 판정하면
  //    안 되는 이유 — MedicalCertificate 가 <dialog> 모달 두 개를
  //    certificateRightColumn 의 직계 자식으로 항상 렌더해서(닫혀 있으면
  //    display:none 이라 레이아웃엔 안 잡히지만 DOM 자식 수엔 잡힌다)
  //    자식이 결코 하나가 되지 않는다. 그래서 핸들(role="separator")이
  //    실제로 있을 때만 :has() 로 gap 을 올리는 별도 규칙이 있어야 한다.
  // 2) align-content: start — 없으면 기본값(normal, 그리드에서 stretch
  //    와 동일)이 남는 공간을 auto 트랙(핸들 트랙)에 나눠 줘서, 핸들이
  //    (ResizeHandle.module.css 의 align-self:center 때문에) 남는 공간
  //    한가운데로 뜬다 — 패널 바로 아래가 아니라.
  it.each(["middleColumn", "certificateRightColumn"])(
    ".%s 는 gap:0 기본값 + role=separator 조건부 gap + align-content:start 를 갖는다",
    (className) => {
      const body = firstRuleBody(css, className);
      expect(body).toMatch(/gap:\s*0\s*;/);
      expect(body).toMatch(/align-content:\s*start\s*;/);

      const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const hasRule = css.match(
        new RegExp(`\\.${escaped}:has\\(>\\s*\\[role="separator"\\]\\)\\s*\\{([^}]*)\\}`)
      );
      expect(hasRule).not.toBeNull();
      expect(hasRule?.[1]).toMatch(/gap:\s*var\(--space-4\)\s*;/);
    }
  );
});
