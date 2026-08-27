# 관리자 콘솔 확장 설계

- 작성일: 2026-08-27
- 대상 프로젝트: BitComputer (EMR + AI 에이전트)
- 선행: Phase A 기반 정비 (`2026-08-26-phase-a-foundation-design.md`) 완료, `main` 병합됨

## 1. 배경

Phase A에서 인증·RBAC·감사 로그를 복구했으나, 관리자가 그 결과를 확인하거나 운영할 화면이 없다. 현재 `/super` 화면은 287줄 단일 파일이며 직원 목록 조회, 역할 변경, 직원 추가 세 가지만 한다.

### 1.1 실제로 막혀 있는 것

**부서를 늘릴 방법이 없다.** `Dept` 엔티티와 테이블은 있으나 조회·생성 API가 없다. `dept` 테이블에는 `id=1, UNASSIGNED` 한 행뿐이고, 이 행은 `DataInitializer`가 부팅 시 upsert한 것이다. 회원가입 화면이 부서 번호를 자유 입력으로 받아 존재하지 않는 값으로 500을 내던 문제(커밋 `82bed60`)는 입력 검증으로 막았지만, 부서를 추가할 수단이 없어 모든 직원이 `UNASSIGNED`에 머문다.

**감사 기록을 볼 방법이 없다.** `GET /api/audit/logs`는 Phase A Task 11에서 만들었고 현재 172건이 쌓여 있으나 UI가 없다. 누가 어떤 환자 기록을 언제 열람했는지, 거부된 접근 시도가 무엇이었는지 확인할 수 없다. 의료 기록 시스템에서 접근 감사는 부가 기능이 아니라 정의적 요구사항이며, RBAC을 켠 의미가 이 화면에서 드러난다.

### 1.2 함께 확인된 사항

- `disease`, `diagnose` 마스터 테이블이 **0건**이다. 상병·처방을 고를 수 없고 AI 처방 추천에도 근거 데이터가 없다. `apps/api/scripts/import_master_codes.py`와 엑셀 원본이 저장소에 있으므로 적재는 가능하다.
- `Employee`에 비활성화를 표현할 필드가 없다. 퇴사자 계정을 막으려면 삭제밖에 없는데, 삭제하면 기존 진료 기록의 작성자 참조가 끊긴다.

## 2. 범위와 단계

5개 기능을 두 단계로 나눈다. 분기 기준은 "지금 막혀 있는가"이다.

| 단계 | 기능 | 근거 |
|---|---|---|
| **1** | 감사 로그 조회 | API는 있으나 볼 수단이 없음 |
| **1** | 부서 관리 (목록·추가·이름 수정) | 부서를 늘릴 수단이 없음 |
| **1** | `/admin` 라우팅·API 재편 | 2단계가 이 구조 위에 붙음 |
| 2 | 직원 상세·수정·비활성화 | 있으면 좋음. 스키마 변경 동반 |
| 2 | 시스템 상태 대시보드 | 있으면 좋음 |
| 2 | 상병·처방 마스터 조회 | 엑셀 적재가 선행돼야 의미 있음 |

1단계와 2단계는 각각 별도의 구현 계획을 갖는다. 본 문서는 전체 설계를 담되, 2단계는 개요 수준으로만 기술한다 — 1단계 구현 후 다시 구체화한다.

### 2.1 명시적 제외

- **마스터 코드 수정 기능을 만들지 않는다.** 상병 코드는 표준 코드이고, 화면에서 임의 수정하면 진료 기록의 코드 참조가 깨진다. 갱신은 엑셀 재적재로만 한다. 2단계의 마스터 화면은 조회·검색 전용이다.
- **부서 삭제를 만들지 않는다.** 직원이 참조 중인 부서를 지우면 FK 위반이며, 그것이 방금 고친 500의 원인이었다. 쓰지 않는 부서는 남겨둔다.
- Phase A의 이월 항목(9개 컨트롤러 테스트의 `standaloneSetup`, AI 엔드포인트 감사 로그의 null `targetPatientId` 등)은 이 작업 범위가 아니다.

## 3. 라우팅과 API 재편

### 3.1 `/super` → `/admin`

프론트 라우트, API 경로, 컨트롤러 이름을 모두 `admin`으로 통일한다. 사용자가 한 명뿐인 포트폴리오이므로 호환성 부담이 없다.

| 대상 | 변경 전 | 변경 후 |
|---|---|---|
| 프론트 라우트 | `app/(auth)/super/` | `app/(auth)/admin/` |
| API 클라이언트 | `services/super.ts` | `services/admin.ts` |
| 컨트롤러 | `SuperUserController` | `AdminController` |
| API 경로 | `/api/super/**` | `/api/admin/**` |
| RBAC 매처 | `.requestMatchers("/api/super/**", "/api/audit/**")` | `.requestMatchers("/api/admin/**", "/api/audit/**")` |

역할 이름 `SUPER_USER`는 그대로 둔다 — `Role` enum 값 변경은 토큰 claim과 DB 값에 모두 영향을 주고 얻는 것이 없다.

### 3.2 프론트 구조

```
apps/web/src/app/(auth)/admin/
├── layout.tsx          공통 사이드바 + SUPER_USER 가드
├── page.tsx            /admin 진입 시 /admin/audit 로 리다이렉트
├── audit/page.tsx      감사 로그 조회          [1단계]
├── depts/page.tsx      부서 관리               [1단계]
├── users/page.tsx      직원 관리               [1단계에서 기존 기능 이관]
├── master/page.tsx     마스터 조회             [2단계]
└── status/page.tsx     시스템 상태             [2단계]
```

역할 확인을 `layout.tsx`에서 한 번만 하고 하위 화면은 반복하지 않는다. 각 화면은 독립 파일이며 200줄 내외를 목표로 한다 — 이 저장소에는 이미 695줄 `evaluation/page.tsx`, 685줄 `Diagnosis.tsx` 같은 파일이 있고 그 패턴을 늘리지 않는다.

1단계에서 기존 `/super/page.tsx`의 직원 목록·역할 변경·직원 추가 기능을 `/admin/users/page.tsx`로 옮긴다. 기능 추가 없이 이동만 한다 — 직원 상세·수정·비활성화는 2단계다.

### 3.3 API 목록

**1단계**

| 메서드 | 경로 | 권한 | 용도 |
|---|---|---|---|
| GET | `/api/depts` | 인증된 실제 역할 | 부서 목록 (직원 추가 폼의 select) |
| POST | `/api/admin/depts` | SUPER_USER | 부서 추가 |
| PUT | `/api/admin/depts/{id}` | SUPER_USER | 부서명 수정 |
| GET | `/api/audit/logs` | SUPER_USER | **기존 API에 필터 파라미터 추가** |
| GET | `/api/admin/users` | SUPER_USER | 기존 `get_all_users` 경로 이동 |
| POST | `/api/admin/users` | SUPER_USER | 기존 `create_user` 경로 이동 |
| PUT | `/api/admin/users/{id}/role` | SUPER_USER | 기존 `set_role/{id}` 경로 이동 |

`GET /api/depts`만 `/api/admin/` 밖에 두는 이유: 직원 추가 폼에서 부서를 고르려면 목록이 필요하고, 향후 `SUPER_USER`가 아닌 화면에서도 부서명을 표시할 수 있다. 부서명은 민감 정보가 아니다. RBAC은 `anyRequest().hasAnyRole(RECEPTIONIST, NURSE, DOCTOR, SUPER_USER)` 규칙에 걸린다.

**2단계 (개요)**

`GET/PUT /api/admin/users/{id}`, `POST /api/admin/users/{id}/deactivate`, `POST /api/admin/users/{id}/reactivate`, `GET /api/admin/system-status`.

마스터 조회는 기존 `GET /api/diseases`, `GET /api/diagnoses`를 재사용하며 새 API를 만들지 않는다.

## 4. 감사 로그 조회 (1단계 핵심)

### 4.1 필터

현재 `GET /api/audit/logs`는 `page`, `size`만 받는다. 다음 파라미터를 추가한다. 모두 선택이며, 없으면 전체를 대상으로 한다.

| 파라미터 | 타입 | 의미 |
|---|---|---|
| `actorUsername` | String | 행위자 계정 (부분 일치) |
| `targetPatientId` | Integer | 대상 환자 |
| `action` | String | 행위 종류 (정확 일치) |
| `outcome` | String | `GRANTED` / `DENIED` / `CSRF_REJECTED` |
| `from` | LocalDateTime | 기간 시작 (포함) |
| `to` | LocalDateTime | 기간 끝 (포함) |

정렬은 `occurredAt` 내림차순 고정이다. 감사 로그를 다른 순서로 보고 싶은 상황이 떠오르지 않으므로 정렬 파라미터를 만들지 않는다.

구현은 `AccessAuditLogRepository`에 `JpaSpecificationExecutor`를 붙이고 `Specification`을 조합한다. 파라미터가 6개이고 조합이 자유로워 메서드 이름 기반 쿼리로는 감당되지 않는다.

### 4.2 화면

- 상단에 필터 폼, 하단에 결과 테이블과 페이징
- 컬럼: 시각, 행위자(계정·역할), 행위, 대상 환자, 결과, IP, 상세
- `DENIED`와 `CSRF_REJECTED` 행은 배경색으로 구분한다. 감사 화면을 여는 주된 이유가 거부된 시도를 찾는 것이기 때문이다
- 기본 조회는 필터 없이 최신 50건

비활성 계정의 과거 행위는 그대로 표시된다. 감사 로그는 `actorUsername`을 문자열로 저장하므로 계정 상태와 무관하다 — 별도 처리가 필요 없다.

### 4.3 감사 로그 자체의 감사

`GET /api/audit/logs` 조회에는 `@AuditPatientAccess`를 붙이지 않는다. 감사 로그 조회를 감사 로그에 남기면 조회할 때마다 행이 늘어 신호 대 잡음비가 나빠진다. 필요해지면 별도 저장소로 분리해야 할 문제이지, 같은 테이블에 섞을 일이 아니다.

## 5. 부서 관리 (1단계)

### 5.1 API 동작

- `POST /api/admin/depts` — 부서명 중복 시 409. 빈 문자열·공백만 있는 이름은 400
- `PUT /api/admin/depts/{id}` — 존재하지 않는 id는 404, 다른 부서와 이름 중복은 409
- `GET /api/depts` — id 오름차순 전체 반환. 부서 수가 수십 단위를 넘을 일이 없어 페이징하지 않는다

`Dept` 엔티티의 `dept` 컬럼에 unique 제약이 없으므로 서비스 계층에서 중복을 확인한다. 스키마에 unique 제약을 추가하는 것은 기존 데이터 검증이 필요해 이번 범위에 넣지 않는다.

### 5.2 화면

부서 목록과 추가 폼. 이름 수정은 인라인 편집. 각 부서에 소속 직원 수를 함께 표시해 어느 부서가 실제로 쓰이는지 보이게 한다.

## 6. 데이터 모델 변경

1단계에는 스키마 변경이 없다.

2단계에서 `Employee`에 `deactivated_at DATETIME NULL`을 추가한다. `null`이면 활성이다. 비활성 계정은 로그인 시 `InvalidCredentialsException`으로 거부한다 — 계정 상태를 응답으로 노출하지 않기 위해 자격증명 오류와 동일하게 취급한다. 기존 진료 기록의 작성자 참조는 유지된다.

`ddl-auto=update`이므로 컬럼은 자동 생성되고 기존 16개 행은 `null`(활성)로 남는다. 이것이 의도한 동작이다.

## 7. 선행 작업 — 마스터 코드 적재

2단계의 마스터 조회 화면 이전에 실데이터가 있어야 한다. 1단계와 병행 가능하다.

```bash
python -m pip install openpyxl
python apps/api/scripts/import_master_codes.py
```

`apps/api/상병코드.xlsx`와 `처방코드.xlsx`를 읽어 `disease`, `diagnose` 테이블에 적재한다. 스크립트는 적재 전 두 테이블을 비우고 auto increment를 재설정한다.

적재 후 `disease`, `diagnose` 건수를 확인하고 `GET /api/diseases?page=0&size=5`가 결과를 반환하는지 검증한다.

## 8. 검증

### 8.1 백엔드

- 권한: `DOCTOR` 토큰으로 `/api/admin/**` 접근 시 403
- 부서: 중복 이름 409, 빈 이름 400, 없는 id 수정 404
- 감사 필터: 각 파라미터가 실제로 결과를 좁히는지. 172건의 기존 데이터로 확인 가능
- 경로 이동: 기존 `/api/super/**` 경로가 더 이상 존재하지 않는지 (404)

### 8.2 프론트

vitest로 각 화면의 렌더링과 주요 상호작용을 확인한다. 감사 화면은 필터 적용 시 요청 파라미터가 올바르게 구성되는지, 부서 화면은 추가·수정 폼이 동작하는지.

### 8.3 E2E

1단계에 한 가지를 추가한다.

```
SUPER_USER 로그인
  -> 부서 생성
  -> 그 부서로 직원 생성
  -> 감사 로그 조회에서 방금 만든 직원의 행위가 검색되는지 확인
```

2단계에서는 비활성화 후 로그인 거부를 추가한다.

## 9. 완료 조건 (1단계)

1. `/admin`으로 진입하면 감사 로그 화면이 열리고, `SUPER_USER`가 아니면 접근할 수 없다
2. 감사 로그를 행위자·환자·행위·결과·기간으로 걸러 볼 수 있다
3. `DENIED` 행이 시각적으로 구분된다
4. 부서를 추가할 수 있고, 직원 추가 폼의 부서가 select로 바뀌어 자유 입력이 불가능하다
5. 기존 `/api/super/**` API 경로와 `/super` 프론트 라우트가 모두 존재하지 않는다
6. `DOCTOR` 토큰으로 `/api/admin/**` 접근 시 403
7. 백엔드·프론트 테스트와 E2E가 통과하고 CI가 green이다

## 10. 다음 단계

1단계 완료 후 2단계(직원 상세·수정·비활성화, 시스템 상태 대시보드, 마스터 조회)를 별도 계획으로 구체화한다. 시스템 상태 대시보드는 `LLM_PROVIDER`와 X-ray 엔진 상태를 함께 노출해, 지금 mock으로 돌고 있는지 한눈에 보이게 하는 것이 목표다.
