import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

/**
 * RTL 의 `findBy*`/`waitFor` 계열 기본 비동기 예산은 1000ms 다. 이 값은
 * "로직상 얼마나 걸려야 맞는가" 가 아니라 "얼마나 오래 기다려 줄 것인가"
 * 를 정할 뿐이다 — MedicalCertificate.test.tsx 의 `findByRole("dialog")`
 * 가 전체 스위트를 병렬 워커로 돌릴 때만(단독 실행 25회는 0회 실패) 28회
 * 중 2회 실패한 사례가 이를 보여준다: click → 비동기 핸들러 → mock promise
 * resolve → setState → Modal 의 showModal() 호출로 이어지는 체인 자체는
 * 정상이고, 워커 기아 상태에서 스케줄이 밀려 1초를 넘길 뿐이다. 이 파일과
 * MedicalCertificate.tsx, ui/Modal.tsx 는 리사이즈 브랜치 이전과 바이트
 * 동일해 새 로직 결함이 아니라 기존 결함이다.
 *
 * 같은 클릭 → 비동기 → Modal 체인을 쓰는 다른 테스트도 같은 위험을 안고
 * 있으므로 특정 파일 하나에만 `{ timeout: ... }` 을 박지 않고 전역으로
 * 올린다 — 그래야 이 트레이드오프가 한 곳에 드러난다.
 *
 * 대가: 이 값을 올리면 진짜로 멈춘 테스트(예: mock 이 결코 resolve 되지
 * 않는 경우)를 알아채는 데 그만큼(최대 5배) 더 오래 걸린다. "빨리 실패"
 * 보다 "병렬 부하에서 안정적으로 통과" 를 택한 것이다.
 */
configure({ asyncUtilTimeout: 5000 });
