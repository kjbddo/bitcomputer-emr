# 프론트엔드 디자인 시스템 재구성 설계

**작성일:** 2026-08-27
**대상:** `apps/web`
**선행 관계:** 관리자 콘솔 1단계 Task 5·6·7 **이전**에 완료한다.

---

## 1. 배경과 문제 정의

### 1.1 사용자 요구

기능은 문제없다. 현재 화면의 UI가 세련되지 못하다. 다크 모드/라이트 모드를 원한다.

### 1.2 실제 진단

"CSS를 다듬으면 되는" 문제가 아니다. **디자인 시스템이 존재하지 않는다.**

| 증상 | 근거 |
|---|---|
| 디자인 토큰 없음 | CSS module 27개 5,341줄. 색상 리터럴(`#rrggbb`/`rgb()`/`rgba()`) 약 700개가 파일마다 흩어져 있음. `globals.css`의 `--background`/`--foreground` 2개가 정의된 토큰의 전부이며, 이를 참조하는 컴포넌트는 0개 |
| 팔레트가 4갈래로 분기 | Header `#2563eb`(파랑) / Sidebar `#333336`(진회색) / 콘텐츠 배경 `#5E5E61`(중간 회색) / 관리자 사이드바 `#fafafa` + active `#1a4f8a`(다른 파랑) |
| 패널 셸이 17번 중복 구현 | 17개 CSS module이 각자 `.header`/`.title` 규칙을 손으로 정의. 패딩·폰트 크기·경계선이 파일마다 다름 |
| 모달이 4번 중복 구현 | `ChatbotPopup`, `Diagnosis`, `MedicalCertificate`, `SearchPatientModal`이 각각 `position: fixed` 오버레이를 자체 구현. `<dialog>` 사용 0건, Escape 키 처리 0건, 포커스 트랩 0건 |
| **다크 모드는 없는 게 아니라 깨져 있음** | `globals.css`가 `prefers-color-scheme: dark`에서 `--background`/`--foreground`를 뒤집지만 이 변수를 쓰는 컴포넌트가 없다. OS 다크 모드를 켜면 어두운 `body` 위에 하드코딩된 밝은 패널이 얹히고 상속 글자색만 뒤집혀 대비가 무너진다. 현 상태는 "미구현"보다 나쁘다 |
| 인증 화면은 CSS module조차 없음 | `login/page.tsx`, `signup/page.tsx`가 인라인 `style={{}}`. 나머지 앱과 시각 언어가 완전히 다름 |
| 폰트가 적용된 적 없음 | `layout.tsx`가 `Geist`를 로드해 `--font-geist-sans`를 심지만 `globals.css`의 `body`가 `font-family: Arial, Helvetica`로 덮어씀. 게다가 `subsets: ["latin"]`이라 한글 글리프 커버리지는 0 |
| 스캐폴딩 잔존 | metadata `title: "Create Next App"`, `<html lang="en">`(한국어 앱), Next 스타터 `src/app/page.module.css` 199줄(루트 `page.tsx`가 `return null`이라 죽은 코드) |
| 셸이 두 벌 | 대시보드는 `Header` + `Sidebar`, 관리자 콘솔은 자체 `layout.module.css`. 관리자 화면에는 헤더가 아예 없어 대시보드로 돌아갈 경로도, 로그아웃 버튼도 없다 |

**결론:** 토큰 레이어를 도입하고 반복 구현된 셸을 공용 프리미티브로 흡수한다. 그 위에서 전 화면을 재스킨한다.

### 1.3 리스크 조사 결과 — 재스킨 리스크는 낮다

| 항목 | 사실 | 함의 |
|---|---|---|
| E2E 테스트 | `tests/e2e/`는 `httpx` 기반 **API 레벨** 테스트. 브라우저를 띄우지 않음 | CSS/DOM 변경이 E2E를 깰 수 없음 |
| 프론트 단위 테스트 | `AIReport.test.tsx` 1개뿐. `findByRole("button", {name})`, `findByRole("status")`, `getByText` 사용 | **시맨틱 요소와 접근성 이름을 보존**하면 안전. class 이름은 자유 |
| `data-testid` | 코드베이스 전체 0건 | class 이름에 결합된 테스트 없음 |

따라서 제약은 하나다: **DOM의 시맨틱(요소 종류, role, 접근성 이름)을 보존한다. 클래스 이름과 시각 표현은 자유롭게 바꾼다.**

---

## 2. 채택한 방향

### 2.1 범위 (사용자 선택)

**토큰 + 공용 프리미티브 + 전면 재스킨.**

포함: 토큰 레이어, 테마 전환, 공용 프리미티브 7종, CSS module 27개 재작성, 인라인 스타일 7개 파일 정리, 폰트·metadata·서비스명 수정, 검증 장치 3종.

**그리드 골격(3컬럼 구성, 컬럼 폭, 반응형 breakpoint)과 DOM 구조는 유지한다.** 재구성은 표면(색·여백·타이포·경계·모서리·상태 표현)에서 일어난다.

### 2.2 시각 방향 (사용자 선택)

**A 골격 + B 여백.** slate 중성 팔레트와 파랑 강조는 고밀도 데이터 앱(A) 그대로 가되, 패딩과 행 간격은 넉넉한 쪽(B) 수준으로 올린다.

구체적 귀결:
- 그림자는 기본 표면에서 쓰지 않는다. 평면 + 헤어라인 경계로 층을 표현한다. 그림자는 떠 있는 것(모달, 팝오버, 드롭다운)에만.
- 패널 내부 패딩 16px(현재 다수가 8~12px), 데이터 행 높이 36px, 패널 간 간격 16px, 패널 내 섹션 간격 12px.
- 강조색은 화면당 실질 1개. 나머지는 중성색. 역할색(success/warning/danger)은 상태 표현에만.

### 2.3 서비스명 (사용자 지시)

`슈붕보다팥붕` → **`BitComputer EMR`**

---

## 3. 아키텍처

```
apps/web/src/
  styles/
    tokens.css          원시 램프 + 의미 토큰. 색상 리터럴이 존재하는 유일한 파일
    reset.css           박스 모델, 마진 초기화, 포커스 가시성
  app/
    globals.css         tokens.css/reset.css import + body 타이포 + color-scheme
    layout.tsx          lang="ko", metadata, 폰트 변수, 테마 부트 스크립트
    theme-script.ts     hydration 이전에 실행되는 인라인 스크립트 문자열
    styleguide/page.tsx 개발 전용 프리미티브 카탈로그
  components/
    ui/
      Panel.tsx       Panel.module.css
      Button.tsx      Button.module.css
      Field.tsx       Field.module.css
      Table.tsx       Table.module.css
      Badge.tsx       Badge.module.css
      Modal.tsx       Modal.module.css
      EmptyState.tsx  EmptyState.module.css
      ThemeToggle.tsx ThemeToggle.module.css
      index.ts
    theme/
      ThemeProvider.tsx   테마 상태(system|light|dark) 컨텍스트
```

### 3.1 레이어 규칙

```
1. 원시 램프    --slate-50..950, --blue-*, --green-*, --amber-*, --red-*
                리터럴 hex. 두 테마에서 동일한 픽셀값. 컴포넌트가 직접 참조 금지
2. 의미 토큰    --surface-*, --text-*, --border-*, --accent-*, --success-* ...
                테마별로 1번 램프의 다른 stop을 가리킨다
3. 치수 토큰    --space-*, --radius-*, --font-size-*, --line-height-*,
                --shadow-*, --dur-*, --ease-*   (테마 불변)
```

**컴포넌트는 2·3번만 참조한다.** 1번을 직접 쓰면 다크 모드에서 뒤집히지 않는다. 이 규칙은 §7.2의 가드 테스트가 강제한다.

---

## 4. 토큰 정의

### 4.1 원시 램프

```css
--slate-50:#F8FAFC; --slate-100:#F1F5F9; --slate-200:#E2E8F0; --slate-300:#CBD5E1;
--slate-400:#94A3B8; --slate-500:#64748B; --slate-600:#475569; --slate-700:#334155;
--slate-800:#1E293B; --slate-900:#0F172A; --slate-950:#020617;

--blue-100:#DBEAFE; --blue-400:#60A5FA; --blue-600:#2563EB; --blue-700:#1D4ED8; --blue-950:#172554;
--green-100:#DCFCE7; --green-300:#86EFAC; --green-600:#16A34A; --green-800:#166534; --green-950:#14532D;
--amber-100:#FEF3C7; --amber-300:#FCD34D; --amber-600:#D97706; --amber-800:#92400E; --amber-950:#451A03;
--red-100:#FEE2E2;  --red-300:#FCA5A5;  --red-600:#DC2626;  --red-800:#991B1B;  --red-950:#450A0A;
```

### 4.2 의미 토큰

| 토큰 | 라이트 | 다크 | 용도 |
|---|---|---|---|
| `--surface-canvas` | slate-100 | slate-900 | 페이지 배경 (현재 `#5E5E61` 자리) |
| `--surface-sunken` | slate-200 | slate-950 | 우묵한 영역, 테이블 헤더 |
| `--surface-raised` | `#FFFFFF` | slate-800 | 패널, 카드, 입력 필드 |
| `--surface-overlay` | `#FFFFFF` | `#293548` | 모달, 팝오버, 드롭다운 |
| `--surface-chrome` | slate-900 | slate-950 | 상단 헤더 · 사이드바 |
| `--text-primary` | slate-900 | slate-100 | 본문 |
| `--text-secondary` | slate-700 | slate-300 | 보조 설명 |
| `--text-muted` | slate-600 | slate-400 | 라벨, placeholder, 메타데이터 |
| `--text-on-chrome` | slate-200 | slate-200 | `--surface-chrome` 위 텍스트 |
| `--text-on-fill` | `#FFFFFF` | `#FFFFFF` | 채워진 버튼 위 텍스트 |
| `--border` | slate-200 | slate-700 | 장식용 헤어라인 (패널 가장자리, 행 구분선) |
| `--border-strong` | slate-300 | slate-600 | 강조 구분선 |
| `--border-control` | slate-500 | slate-400 | **상호작용 요소의 경계** (input, select, textarea, secondary 버튼, 체크박스) |
| `--accent-fill` | blue-600 | blue-600 | 기본 버튼 배경 (두 테마 동일) |
| `--accent-fill-hover` | blue-700 | blue-700 | |
| `--accent-text` | blue-700 | blue-400 | 링크, 활성 탭 |
| `--accent-bg` | blue-100 | blue-950 | 선택된 행, 활성 내비 항목 |
| `--focus-ring` | blue-600 | blue-400 | `:focus-visible` 윤곽 |
| `--success-bg` / `--success-text` | green-100 / green-800 | green-950 / green-300 | 완료 상태 |
| `--warning-bg` / `--warning-text` | amber-100 / amber-800 | amber-950 / amber-300 | 경고, stub 엔진 배지 |
| `--danger-bg` / `--danger-text` | red-100 / red-800 | red-950 / red-300 | 오류, 감사 로그 DENIED 행 |
| `--danger-fill` | red-600 | red-600 | 파괴적 버튼 |

위 stop 배정은 §7.1의 전 쌍에 대해 실제로 계산해 확정한 값이다. 근거가 되는 세 가지 결정:

- **`--accent-fill`·`--danger-fill`은 두 테마에서 같은 값이다.** 흰 글자와의 대비가 4.5:1을 넘는 stop이 각각 blue-600(5.17), red-600(4.83)뿐이다. 다크에서 더 밝은 stop(blue-400 등)으로 바꾸면 흰 글자 대비가 4:1 아래로 떨어진다.
- **라이트의 `--text-secondary`/`--text-muted`가 slate-700/600이다.** slate-600/500 조합에서는 `--text-muted`가 `--surface-canvas`(slate-100) 위에서 4.34:1로 기준 미달이었다.
- **경계 토큰이 3종으로 나뉘어 있다.** `--border`와 `--border-strong`은 장식용 구분선이라 대비 요구가 없다(WCAG 1.4.11은 UI 요소의 경계에만 적용된다). 상호작용 요소의 경계는 3:1을 만족해야 하므로 `--border-control`을 따로 둔다 — slate-300은 흰 배경에서 1.48:1이라 입력 필드 테두리로 쓸 수 없다.

**임상 상태는 새 색을 만들지 않고 위 역할색에 매핑한다.**

| 상태 | 토큰 |
|---|---|
| 대기 | `--accent-bg` / `--accent-text` |
| 진료중 | `--warning-bg` / `--warning-text` |
| 완료 | `--success-bg` / `--success-text` |
| 취소·거부 | `--danger-bg` / `--danger-text` |

### 4.3 치수 토큰

```css
--space-1:4px;  --space-2:8px;  --space-3:12px; --space-4:16px;
--space-5:20px; --space-6:24px; --space-8:32px; --space-10:40px;

--radius-sm:4px; --radius-md:6px; --radius-lg:10px; --radius-full:999px;

--font-size-xs:12px;   --line-height-xs:1.5;
--font-size-sm:13px;   --line-height-sm:1.55;
--font-size-base:14px; --line-height-base:1.6;
--font-size-lg:16px;   --line-height-lg:1.5;
--font-size-xl:20px;   --line-height-xl:1.4;

--row-height:36px;
--control-height:36px;
--control-height-sm:30px;

--shadow-sm:0 1px 2px rgb(15 23 42 / 0.06);
--shadow-md:0 4px 12px rgb(15 23 42 / 0.10);
--shadow-lg:0 12px 32px rgb(15 23 42 / 0.16);

--dur-fast:120ms; --dur-base:200ms;
--ease:cubic-bezier(0.2, 0, 0, 1);
```

다크 테마에서 그림자 alpha는 각각 0.30 / 0.40 / 0.55로 올린다. 어두운 배경에서 같은 alpha는 보이지 않는다.

### 4.4 폰트

```css
--font-sans: var(--font-geist-sans), "Pretendard Variable", Pretendard,
             -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
--font-mono: var(--font-geist-mono), "D2Coding", ui-monospace, monospace;
```

라틴 문자·숫자는 Geist가 처리하고 한글은 플랫폼 폰트로 폴백한다. 빌드 타임 폰트 다운로드를 추가하지 않는다. 현재 Docker 빌드가 `npm run build` 시 `next/font/google`로 Geist를 이미 받고 있으므로 Geist는 유지한다.

`globals.css`의 `body`가 `--font-sans`를 실제로 쓰도록 고친다. 현재 `Arial, Helvetica`가 이를 덮고 있다.

환자 ID, 상병 코드, 처방 코드, 주민등록번호처럼 자릿수 정렬이 의미를 갖는 값은 `--font-mono`.

---

## 5. 테마 전환

### 5.1 메커니즘 — 의존성 추가 없음

`next-themes`를 쓰지 않는다. 필요한 동작 전체가 40줄 안쪽이다.

**상태 3개:** `system`(기본) / `light` / `dark`. `localStorage.theme`에 `"light"` 또는 `"dark"`만 저장하고, `system`은 **키를 삭제**해 표현한다.

**CSS 캐스케이드 3단:**

```css
:root { /* 라이트 의미 토큰 */ }

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* 다크 의미 토큰 */ }
}

:root[data-theme="dark"] { /* 다크 의미 토큰 (동일 값) */ }
```

이 구조가 만족하는 조건:
- JS가 실행되지 않아도 OS 설정을 따른다(2단).
- 사용자가 라이트를 명시하면 OS가 다크여도 라이트다(2단의 `:not()`).
- 사용자가 다크를 명시하면 OS가 라이트여도 다크다(3단).

다크 값이 두 블록에 중복 선언되므로 두 블록이 어긋나면 테마별로 다른 값이 되는 버그가 생긴다. §7.1 대비 테스트가 두 블록을 각각 파싱해 값이 일치하는지도 검사한다.

### 5.2 FOUC 방지

`layout.tsx`의 `<head>`에 hydration 이전 동기 실행 스크립트를 심는다.

```js
(function(){try{var t=localStorage.getItem("theme");
if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t);}catch(e){}})()
```

저장값이 없으면 속성을 붙이지 않는다. 미디어 쿼리 경로가 처리한다. `try/catch`는 프라이빗 모드에서 `localStorage` 접근이 throw하는 브라우저를 위한 것이다.

`<html>`의 `suppressHydrationWarning`을 유지한다. 스크립트가 서버 렌더 결과와 다른 속성을 붙이기 때문이다.

### 5.3 `color-scheme`

`:root`에 `color-scheme: light`, 다크 블록에 `color-scheme: dark`를 선언한다. 이것이 없으면 네이티브 스크롤바, `<select>` 드롭다운 목록, 날짜 피커, 자동완성 배경이 라이트로 남아 다크 모드에서 눈에 띄게 튄다. 현재 `globals.css`가 `html`에만 `color-scheme: dark`를 걸어 이 문제가 반쯤 존재한다.

### 5.4 `ThemeProvider` / `ThemeToggle`

`ThemeProvider`는 `{ theme: "system" | "light" | "dark", setTheme(t) }`를 제공한다. 마운트 시 `localStorage`를 읽어 상태를 복원하고, `setTheme`은 `data-theme` 속성과 `localStorage`를 함께 갱신한다(`system`이면 둘 다 제거).

`ThemeToggle`은 `<button>` 하나로 3상태를 순환하며 `aria-label`에 현재 상태를 담는다(예: `"테마: 시스템 설정. 클릭하면 라이트"`). 아이콘은 인라인 SVG. Header에 배치한다.

`ThemeProvider`는 `ClientProviders.tsx`에 추가한다.

---

## 6. 공용 프리미티브

모두 `.module.css`를 짝으로 갖고, **`tokens.css` 밖에서 색상 리터럴을 쓰지 않는다.**

### 6.1 `Panel`

```ts
{ title?: ReactNode; actions?: ReactNode; footer?: ReactNode;
  padding?: "none" | "md"; className?: string; children: ReactNode }
```

`--surface-raised` 배경, `--border` 1px, `--radius-lg`, 그림자 없음. `title`이 있으면 헤더 행(`--font-size-sm`, `--text-secondary`, 하단 `--border`)을 렌더하고 `actions`를 오른쪽 끝에 놓는다. `padding="none"`은 `Table`을 가장자리까지 붙일 때 쓴다.

17개 module에 흩어진 `.header`/`.title` 중복이 여기로 흡수된다.

### 6.2 `Button`

```ts
{ variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md"; loading?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>
```

- `primary` — `--accent-fill` + `--text-on-fill`. **화면당 1개**가 원칙.
- `secondary` — 투명 배경 + `--border-control` + `--text-primary`. 기본값.
- `ghost` — 경계 없음, hover 시 `--accent-bg`.
- `danger` — `--danger-fill` + `--text-on-fill`.

`loading`은 비활성 + 스피너.

### 6.3 `Field`

```ts
{ label: string; htmlFor: string; error?: string; hint?: string;
  required?: boolean; children: ReactNode }
```

라벨을 `<label htmlFor>`로 연결하고, `error`가 있으면 `role="alert"`로 렌더하며 `aria-describedby`로 자식 입력에 연결한다.

입력 요소 자체(`input`/`select`/`textarea`)는 `globals.css`에서 전역 스타일링한다 — 테두리 `--border-control`, 배경 `--surface-raised`, 높이 `--control-height`, `:focus-visible` 시 `--focus-ring`. 앱 전역에서 모양이 하나여야 하고, 폼마다 래퍼 컴포넌트를 강제하면 이관 비용만 커진다.

### 6.4 `Table`

```ts
{ dense?: boolean; stickyHeader?: boolean; className?: string; children: ReactNode }
```

`<table>` 시맨틱을 그대로 유지한다(`<thead>`/`<tbody>`/`<th scope>`). 헤더는 `--surface-sunken` + `--text-muted` + `--font-size-xs`, 행 높이 `--row-height`, 행 hover `--accent-bg`, 선택 행 `--accent-bg` + 좌측 2px `--accent-fill`. 얼룩말 줄무늬는 쓰지 않는다. 경계선으로 충분하고 다크 모드에서 지저분해진다.

수평 스크롤은 래퍼의 `overflow-x: auto`가 담당한다. **페이지 본문이 가로로 스크롤되게 두지 않는다.**

### 6.5 `Badge`

```ts
{ tone?: "neutral" | "accent" | "success" | "warning" | "danger"; children: ReactNode }
```

`--*-bg` + `--*-text` 조합. `--radius-sm`, `--font-size-xs`. 대기/진료중/완료 상태, `engineStatus`의 stub 경고, 감사 로그 DENIED 표시에 쓴다.

### 6.6 `Modal`

```ts
{ open: boolean; onClose: () => void; title: string;
  footer?: ReactNode; size?: "sm" | "md" | "lg"; children: ReactNode }
```

**네이티브 `<dialog>` + `showModal()`을 쓴다.** 포커스 트랩, Escape 닫기, top-layer 스태킹, `::backdrop`을 브라우저가 제공하므로 직접 구현할 코드가 사라진다. `onClose`는 `cancel`/`close` 이벤트에 연결한다. 닫힐 때 열기 전 포커스로 복귀한다.

현재 4곳(`ChatbotPopup`, `Diagnosis`, `MedicalCertificate`, `SearchPatientModal`)의 자체 `position: fixed` 오버레이가 여기로 흡수된다. 이 4곳은 지금 Escape 키도 포커스 트랩도 없다. 이관이 접근성 결함 4건을 동시에 없앤다.

### 6.7 `EmptyState`

```ts
{ title: string; description?: string; action?: ReactNode }
```

빈 목록 자리에 쓴다. 현재 여러 패널이 빈 상태에서 아무것도 렌더하지 않아 로딩 실패와 구분되지 않는다.

---

## 7. 검증 장치

이 절이 "다크 모드 됐습니다"와 "다크 모드가 성립함을 증명함"을 가른다. 프로젝트 전반의 원칙인 **증명 가능성**을 따른다.

### 7.1 대비비 테스트 — `src/styles/__tests__/contrast.test.ts`

`tokens.css`를 읽어 `:root`, `:root[data-theme="dark"]`, 미디어 쿼리 내부 다크 블록의 커스텀 프로퍼티를 파싱하고, 원시 램프까지 해석해 실제 hex를 얻는다. 그 위에서 WCAG 2.1 상대 휘도 공식으로 대비비를 계산한다.

**단언 대상 쌍(두 테마 각각):**

| 전경 | 배경 | 최소 |
|---|---|---|
| `--text-primary` | `--surface-canvas`, `--surface-raised`, `--surface-sunken` | 4.5 |
| `--text-secondary` | `--surface-raised`, `--surface-canvas` | 4.5 |
| `--text-muted` | `--surface-raised`, `--surface-canvas` | 4.5 |
| `--text-on-chrome` | `--surface-chrome` | 4.5 |
| `--text-on-fill` | `--accent-fill`, `--danger-fill` | 4.5 |
| `--accent-text` | `--surface-raised` | 4.5 |
| `--success-text` | `--success-bg` | 4.5 |
| `--warning-text` | `--warning-bg` | 4.5 |
| `--danger-text` | `--danger-bg` | 4.5 |
| `--border-control` | `--surface-raised`, `--surface-canvas` | 3.0 |
| `--focus-ring` | `--surface-raised`, `--surface-canvas` | 3.0 |

텍스트 쌍은 WCAG AA 본문 기준 4.5:1, 비텍스트 UI 경계(`--border-control`, `--focus-ring`)는 WCAG 1.4.11 기준 3:1을 적용한다.

`--border`와 `--border-strong`은 **단언 대상이 아니다.** 장식용 구분선이며 WCAG 1.4.11의 적용 대상이 아니다. 상호작용 요소의 경계에는 `--border-control`을 쓴다.

위 표의 전 쌍은 §4.2 stop 배정으로 두 테마에서 통과함을 확인했다. 라이트 기준 대표값: `--text-primary` 17.85, `--text-secondary` 10.35, `--text-muted` 7.58(모두 `--surface-raised` 위).

**추가 단언:** 다크 값이 두 블록(미디어 쿼리 / `[data-theme="dark"]`)에 중복 선언되므로, 두 블록의 모든 토큰 값이 서로 **일치**하는지도 검사한다.

### 7.2 하드코딩 가드 테스트 — `src/styles/__tests__/no-hardcoded-color.test.ts`

`src/**/*.module.css`와 `src/app/globals.css`를 스캔해 `#rgb`/`#rrggbb`/`#rrggbbaa`, `rgb(`, `rgba(`, `hsl(`, `hsla(`가 나오면 파일명·줄번호와 함께 실패시킨다. 허용 파일은 `tokens.css` 하나다.

`.tsx`의 인라인 `style={{ color: "#..." }}`도 같은 규칙으로 스캔한다.

스캔 대상 디렉터리는 상수로 두고 §8의 단계에 따라 넓힌다. 2단계에서는 `src/styles/`·`src/components/ui/`만, 6단계에서 `src/` 전체로 확대한다.

**이 테스트가 Task 5·6·7이 하드코딩을 다시 들여오는 것을 구조적으로 차단한다.** 규칙을 문서로만 남기면 다음 사람이 지키지 않는다.

### 7.3 스타일가이드 — `src/app/styleguide/page.tsx`

프리미티브 7종을 모든 variant/tone/size 조합으로 렌더하고, 상태 배지 4종과 토큰 팔레트 전체를 보여준다. 테마 토글로 두 모드를 즉시 비교한다.

용도 둘:
1. 재스킨 중 시각적 회귀를 눈으로 잡는 기준 화면.
2. **Task 5(부서 관리)·6(감사 로그)이 참조할 구현 레퍼런스.** 새 화면을 처음부터 토큰 위에 짓게 만든다.

프로덕션 빌드에서는 `NODE_ENV === "production"`일 때 `notFound()`를 호출해 노출하지 않는다.

### 7.4 기존 테스트

`AIReport.test.tsx`가 계속 통과해야 한다. `findByRole("button", {name:"AI 분석"})`, `findByRole("status")`, `getByText("테스트 경고")`가 의존하는 시맨틱을 재스킨이 보존한다는 증거다.

---

## 8. 이관 계획

각 단계는 독립적으로 동작하는 결과물을 낸다.

### 1단계 — 토대
`tokens.css`, `reset.css`, `globals.css` 재작성, `layout.tsx`(`lang="ko"` · metadata · 폰트 변수 · 테마 부트 스크립트), `ThemeProvider`, `ThemeToggle`, 죽은 `page.module.css` 삭제. 대비비 테스트 작성.

이 시점에서 화면은 아직 옛 모습이지만 테마 토글이 동작하고 토큰이 존재한다.

### 2단계 — 프리미티브 + 스타일가이드
`ui/` 7종 + `index.ts` + `/styleguide`.

하드코딩 가드 테스트를 여기서 도입하되 **대상을 `src/styles/`와 `src/components/ui/`로 좁혀서** 시작한다. 3~6단계가 끝나기 전에 전체 범위로 켜면 항상 실패하는 테스트가 되기 때문이다. 6단계에서 전체로 확대한다.

### 3단계 — 앱 셸
`Header`(서비스명 `BitComputer EMR`, `ThemeToggle`, 실제 로그인 사용자), `Sidebar`, `dashboard/page.module.css`, `admin/layout.module.css`.

### 4단계 — 인증 화면
`login`, `signup`의 인라인 스타일을 걷어내고 `Panel`/`Field`/`Button`으로 재구성. `AuthLink`.

### 5단계 — 환자접수 화면
`PatientForm`, `MedicalInfo`, `WaitingStatus`, `SpecialNote`, `History`, `HistoryDiagnose`, `ActionBar`, `PatientInfoBar`, `SearchPatientModal`.

### 6단계 — 진료실 · 진단서 · 기타
`Disease`, `Diagnosis`, `Calender`, `TimeLine`, `ViewDataBase`, `AIReport`, `ChatbotPopup`, `MedicalCertificate`, `CertificateList`, `CertificateBottom`, `CertificatePatientSearch`, `evaluation`, `admin/users`. 가드 테스트를 전체 범위로 확대해 활성화.

---

## 9. 범위 밖

| 항목 | 이유 |
|---|---|
| 내비게이션 구조·화면 구성(IA) 재설계 | 사용자가 "기능적인 건 문제가 안 됨"이라 명시. 이득 대비 리스크가 큼 |
| 모바일 전용 레이아웃 재설계 | 기존 breakpoint(1200/1024/768/640)가 계속 동작하는 선까지만 유지 |
| 새 기능 추가 | 부서 관리·감사 로그 화면은 이 작업 **다음에** Task 5·6에서 이 시스템 위에 짓는다 |
| 관리자 콘솔 2단계 화면 | 별도 spec |
| 백엔드·서비스 변경 | 없음 |

### 9.1 범위에 명시적으로 포함하는 두 가지

둘 다 순수 스타일 작업이 아니지만 해당 파일을 어차피 재작성하므로 함께 처리한다.

1. **`Header`의 하드코딩된 사용자명.** 현재 `<span>김동국</span>`이 박혀 있어 누가 로그인하든 같은 이름이 뜬다. `getMe()`가 이미 존재하므로 실제 사용자명으로 교체한다. 명백한 결함이고 고치는 비용이 거의 없다.

2. **관리자 콘솔의 셸 통일.** 관리자 화면에는 헤더가 없어 대시보드로 돌아갈 경로도 로그아웃도 없다. `admin/layout.tsx`가 같은 `Header`를 쓰고 자체 사이드바는 유지한다. 유일한 구조 변경이며, 되돌아갈 길이 없는 화면을 남겨 두는 쪽이 더 나쁘다고 판단했다.

---

## 10. 리스크

| 리스크 | 완화 |
|---|---|
| 27개 파일 재작성 중 시각적 회귀 | 단계별 이관 + `/styleguide` 기준 화면 + 단계마다 커밋 |
| 재스킨이 `AIReport.test.tsx`를 깸 | 시맨틱 보존이 명시 제약(§1.3). 단계마다 `yarn test` 실행 |
| 다크 값 두 블록이 어긋남 | §7.1이 두 블록 일치를 단언 |
| `<dialog>` 이관 중 기존 모달 동작 변화 | 4곳 각각 열기/닫기/제출 경로를 수동 확인. Escape·포커스 복귀는 **추가되는** 동작이라 회귀가 아님 |
| 폰트 폴백이 플랫폼마다 다르게 보임 | 의도된 동작. 한글 웹폰트를 받지 않는 대가로 수용. 자릿수 정렬이 중요한 값은 `--font-mono`로 고정 |
| 가드 테스트가 6단계 전까지 실패 | 2단계에서 대상을 `styles/`·`ui/`로 좁혀 도입하고 6단계에서 전체로 확대(§8) |

---

## 11. 완료 조건

1. `tokens.css` 밖에 색상 리터럴이 0건이다(가드 테스트 통과).
2. 대비비 테스트가 두 테마의 전 쌍에서 통과한다.
3. 테마 토글이 3상태를 순환하고, 새로고침 후에도 선택이 유지되며, `system` 상태에서 OS 설정을 따른다.
4. JS 비활성 상태에서도 OS 다크 설정이 반영된다.
5. 첫 페인트에 라이트 화면이 번쩍이지 않는다(FOUC 없음).
6. 프리미티브 7종이 `/styleguide`에서 모든 variant로 렌더된다.
7. 인라인 `style={{}}`로 색·간격을 지정하는 곳이 남지 않는다.
8. 모달 4곳이 `<dialog>` 기반 `Modal`을 쓰고 Escape로 닫히며 포커스가 복귀한다.
9. Header가 `BitComputer EMR`과 실제 로그인 사용자를 표시하고, 관리자 콘솔에서도 같은 헤더가 보인다.
10. `AIReport.test.tsx`를 포함한 기존 테스트가 전부 통과한다.
11. `next build`가 경고 없이 성공하고, `docker compose`로 기동한 화면이 두 테마에서 정상 렌더된다.
