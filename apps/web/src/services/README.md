## API Wrapper 사용법 (axios 기반)

### 설치

Yarn 사용 시:

```bash
yarn add axios
```

### 환경 변수

없습니다. `baseURL` 은 비어 있고 요청은 현재 오리진으로 나갑니다.

주소를 환경변수로 받지 않는 이유는 `NEXT_PUBLIC_` 값이 **빌드 시점에 번들에
박히기** 때문입니다. 값이 다른 만큼 프론트 이미지가 갈라져, AWS 용과 DR 용을
따로 구워야 했습니다. 지금은 하나입니다.

프론트와 API 를 같은 호스트명 아래 두는 것이 그 전제입니다 - 배포에서는
CloudFront 가, 로컬에서는 `next.config.ts` 의 rewrite 가 그 조건을 만듭니다.

### 초기화 (선택)

최초 1회 커스텀 옵션으로 인스턴스를 구성할 수 있습니다.

```ts
import { http } from "@services";

// baseURL 을 여기서 절대 주소로 덮으면 그 시점부터 이미지가 환경에 묶입니다.
http({
  timeoutMs: 15000,
});
```

### 인증

인증은 서버가 내려주는 HttpOnly 쿠키(`access_token`)로 처리됩니다. 클라이언트는
토큰 값을 읽거나 저장하지 않으며, `withCredentials: true` 설정으로 쿠키가
자동으로 요청에 실립니다. CSRF 토큰도 `xsrfCookieName`/`xsrfHeaderName` 설정으로
자동 처리됩니다.

### 요청 헬퍼 사용

간단한 CRUD 요청을 위한 헬퍼를 제공합니다.

```ts
import { get, post, put, del } from "@services";

type User = { id: string; name: string };

const me = await get<User>("/users/me");
const created = await post<User, Partial<User>>("/users", { name: "Alice" });
const updated = await put<User, Partial<User>>(`/users/${me.id}`, { name: "Bob" });
await del(`/users/${me.id}`);
```

### 에러 처리

모든 HTTP 에러는 `HttpError`로 throw 됩니다.

```ts
import { get, HttpError } from "@services";

try {
  await get("/users/unknown");
} catch (e) {
  if (e instanceof HttpError) {
    console.error(e.status, e.message, e.data);
  }
}
```

### 엔드포인트 모듈 예시

엔드포인트별 함수를 `src/services/api/*`에 분리해 관리하세요.

```ts
// src/services/api/user.ts
import { get, post } from "@services";

export const fetchMe = () => get<User>("/users/me");
export const createUser = (body: Partial<User>) => post<User, Partial<User>>("/users", body);
```


