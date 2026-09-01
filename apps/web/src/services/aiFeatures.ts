/**
 * 이 배포에 AI 기능이 있는지.
 *
 * DR(재해 복구) 구성은 AI 없이 3-tier 만 세운다. 그때 처방 추천·X-ray 분석
 * 버튼을 그대로 두면 사용자가 눌러서 503 을 받는데, 화면에서는 그것이
 * "이 배포에는 없는 기능" 인지 "지금 고장난 것" 인지 구별되지 않는다.
 * 그래서 아예 렌더하지 않는다.
 *
 * 서버 쪽 짝은 `features.ai.enabled`(apps/api 의 AiFeatures)다. 둘은 각자
 * 자기 값을 읽으므로 어긋날 수 있다 — 웹만 끄면 백엔드는 여전히 동작하고,
 * 백엔드만 끄면 버튼이 남아 503 을 부른다. compose 가 두 값을 같은
 * 출처에서 내려주는 것이 그 어긋남을 막는 유일한 지점이다
 * (`infra/docker-compose.dr.yml`).
 *
 * **기본값은 켜짐이다.** 값이 없을 때 꺼지면 설정 실수 하나로 AI 기능이
 * 조용히 사라지고, 화면에서는 DR 구성과 구별되지 않는다. 끄는 것은 명시적
 * 선택이어야 한다 — 서버 쪽 AiFeatures 와 같은 방향이다.
 *
 * `NEXT_PUBLIC_` 접두가 붙은 값은 **빌드 시점에 번들에 박힌다.** DR 이미지는
 * 이 값을 false 로 두고 따로 빌드해야 하며, 기동 시 환경변수만 바꿔서는
 * 바뀌지 않는다(`infra/docker-compose.dr.yml` 의 build args 참고).
 */
export function isAiEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AI_FEATURES_ENABLED !== "false";
}

/**
 * AI 가 꺼진 배포에서 화면에 남길 문구.
 *
 * 버튼을 지우기만 하면 "원래 없는 기능" 처럼 보인다. 이 배포가 축소 구성이라는
 * 사실 자체는 남겨야, 사용자가 전체 스택을 찾아갈 수 있다.
 */
export const AI_DISABLED_NOTICE =
  "이 배포에는 AI 기능이 포함되어 있지 않습니다(DR 구성).";
