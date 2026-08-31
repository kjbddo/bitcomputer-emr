# 관리자 콘솔 1단계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자가 감사 기록을 조회하고 부서를 관리할 수 있게 한다.

**Architecture:** 기존 `SuperUserController`를 `AdminController`로 옮기며 API 경로를 `/api/admin/**`으로 재편하고, 프론트는 `/admin` 아래 중첩 라우트로 화면을 나눈다. 감사 로그 필터는 `JpaSpecificationExecutor`로 조합하고, 부서 관리는 새 서비스·컨트롤러를 추가한다.

**Tech Stack:** Java 23 / Spring Boot 3.5.6 / Spring Data JPA / MySQL 8 / Next.js 15.5.4 (App Router) / React 19.1.0 / vitest / pytest

**참조 spec:** `Docs/superpowers/specs/2026-08-27-admin-console-design.md` (1단계만)

## Global Constraints

- **Java toolchain 23**, Spring Boot 3.5.6. `build.gradle`의 `JavaLanguageVersion.of(23)`을 변경하지 않는다.
- **응답 본문은 camelCase**, FastAPI 요청 본문은 snake_case. 이 작업은 Spring만 다루므로 전부 camelCase다.
- **CSRF가 활성이다.** 상태 변경 요청(POST/PUT/DELETE)은 `XSRF-TOKEN` 쿠키 값을 `X-XSRF-TOKEN` 헤더에 실어야 한다. `GET`·`HEAD`·`OPTIONS`는 면제.
- **Spring 통합 테스트 규약**: `@SpringBootTest` + `@AutoConfigureMockMvc` + `@ActiveProfiles("test")` + `@Import({TestRedisConfig.class, TestRabbitConfig.class})`. `SecurityMockMvcRequestPostProcessors.csrf()`를 쓰는 테스트 메서드에는 반드시 `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)`를 클래스에 건다 — 그 헬퍼가 리플렉션으로 `CsrfFilter` 싱글턴을 오염시킨다.
- **인증 쿠키 생성 패턴**: `new jakarta.servlet.http.Cookie(CookieFactory.ACCESS_TOKEN_COOKIE, jwtTokenProvider.generateAccessToken("이름", Role.역할))`
- **사전 존재 테스트 실패 3건**(`PatientServiceImplTest` ×2, `WaitingServiceImplTest` ×1)은 고치지 않는다. 카운트가 그 이상 늘면 보고한다.
- **`infra/.env`를 커밋하지 않는다.**
- **커밋 메시지**는 conventional commit prefix + 한국어 본문.
- **역할 이름 `SUPER_USER`는 변경하지 않는다.** 경로만 `admin`으로 바꾼다.

---

## File Structure

### 새로 만드는 파일

| 경로 | 책임 |
|---|---|
| `apps/api/.../controller/DeptController.java` | `GET /api/depts` — 모든 인증 역할이 읽는 부서 목록 |
| `apps/api/.../controller/AdminDeptController.java` | `POST/PUT /api/admin/depts` — SUPER_USER 전용 부서 생성·수정 |
| `apps/api/.../service/DeptService.java` | 부서 조회·생성·수정 + 중복·공백 검증 |
| `apps/api/.../serviceImpl/DeptServiceImpl.java` | 위 구현 |
| `apps/api/.../model/DeptDTO.java` | 부서 응답 (id, dept, employeeCount) — **기존 동명 파일 확인 필요** |
| `apps/api/.../model/DeptCreateRequestDTO.java` | 부서 생성·수정 요청 |
| `apps/api/.../exception/DuplicateDeptNameException.java` | 부서명 중복 → 409 |
| `apps/api/.../Repository/AuditLogSpecifications.java` | 감사 로그 필터 Specification 조합 |
| `apps/api/src/test/java/.../controller/DeptControllerTest.java` | 부서 API 테스트 |
| `apps/api/src/test/java/.../controller/AuditLogFilterTest.java` | 감사 필터 테스트 |
| `apps/web/src/app/(auth)/admin/layout.tsx` | 공통 사이드바 + SUPER_USER 가드 |
| `apps/web/src/app/(auth)/admin/page.tsx` | `/admin/audit`로 리다이렉트 |
| `apps/web/src/app/(auth)/admin/audit/page.tsx` | 감사 로그 화면 |
| `apps/web/src/app/(auth)/admin/depts/page.tsx` | 부서 관리 화면 |
| `apps/web/src/app/(auth)/admin/users/page.tsx` | 직원 관리 (기존 `/super` 이관) |
| `apps/web/src/services/admin.ts` | `services/super.ts` 대체 + 부서·감사 API |
| `apps/web/src/types/audit.ts` | 감사 로그 타입 |
| `apps/web/src/types/dept.ts` | 부서 타입 |

### 수정하는 파일

| 경로 | 변경 |
|---|---|
| `apps/api/.../controller/SuperUserController.java` | → `AdminController.java`로 이름·경로 변경 |
| `apps/api/.../config/SecurityConfig.java` | `/api/super/**` → `/api/admin/**` 매처 |
| `apps/api/.../controller/AuditLogController.java` | 필터 파라미터 추가 |
| `apps/api/.../Repository/AccessAuditLogRepository.java` | `JpaSpecificationExecutor` 상속 |

### 삭제하는 파일

| 경로 | 사유 |
|---|---|
| `apps/web/src/app/(auth)/super/page.tsx` | `/admin/users`로 이관 |
| `apps/web/src/app/(auth)/super/page.module.css` | 위와 동일 |
| `apps/web/src/services/super.ts` | `services/admin.ts`로 대체 |

---

## Task 1: `/api/super` → `/api/admin` 재편

**Files:**
- Rename: `apps/api/src/main/java/com/example/bitcomputer/controller/SuperUserController.java` → `AdminController.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java`
- Test: `apps/api/src/test/java/com/example/bitcomputer/config/SecurityConfigTest.java`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `/api/admin/users` (GET), `/api/admin/users` (POST), `/api/admin/users/{id}/role` (PUT). 이후 프론트 태스크가 이 경로를 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`SecurityConfigTest`에 추가한다. 기존 파일의 import와 필드 선언을 그대로 쓴다.

```java
    @Test
    void oldSuperPathNoLongerExists() throws Exception {
        mockMvc.perform(get("/api/super/get_all_users")
                       .cookie(cookieFor(Role.SUPER_USER)))
               .andExpect(status().isNotFound());
    }

    @Test
    void adminUsersPathRequiresSuperUser() throws Exception {
        mockMvc.perform(get("/api/admin/users")
                       .cookie(cookieFor(Role.DOCTOR)))
               .andExpect(status().isForbidden());
    }

    @Test
    void adminUsersPathAllowsSuperUser() throws Exception {
        mockMvc.perform(get("/api/admin/users")
                       .cookie(cookieFor(Role.SUPER_USER)))
               .andExpect(status().isOk());
    }
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*SecurityConfigTest*'
```

Expected: `adminUsersPathAllowsSuperUser`가 404로 실패 (경로 없음), `oldSuperPathNoLongerExists`는 200을 받아 실패.

- [ ] **Step 3: 컨트롤러 이름·경로 변경**

```bash
cd apps/api/src/main/java/com/example/bitcomputer/controller
git mv SuperUserController.java AdminController.java
```

`AdminController.java`에서 클래스 선언부와 매핑을 바꾼다.

```java
@RestController
@RequestMapping("/api/admin")
public class AdminController {
```

메서드 매핑도 spec의 새 경로로 바꾼다.

```java
    @PutMapping("/users/{id}/role")
    public ResponseEntity<String> setRole(
```

```java
    @PostMapping("/users")
    public ResponseEntity<String> createUser(
```

```java
    @GetMapping("/users")
    public ResponseEntity<?> getAllEmployees(
```

생성자 이름도 `AdminController`로 바꾼다.

- [ ] **Step 4: SecurityConfig 매처 수정**

```bash
cd /c/Users/kjbdd/Projects/BitComputer
sed -i 's|"/api/super/\*\*", "/api/audit/\*\*"|"/api/admin/**", "/api/audit/**"|' \
  apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java
grep -n '"/api/admin/\*\*"' apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java
```

Expected: `.requestMatchers("/api/admin/**", "/api/audit/**").hasRole("SUPER_USER")`

- [ ] **Step 5: 잔존 참조 확인**

```bash
grep -rn "api/super\|SuperUserController" apps/api/src apps/web/src tests/ 2>/dev/null | grep -v node_modules
```

Expected: `apps/web/src/services/super.ts`의 3개 경로만 남는다 (Task 4에서 처리). 백엔드에는 없어야 한다.

- [ ] **Step 6: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*SecurityConfigTest*'
```

Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/controller/AdminController.java \
        apps/api/src/main/java/com/example/bitcomputer/config/SecurityConfig.java \
        apps/api/src/test/java/com/example/bitcomputer/config/SecurityConfigTest.java
git commit -m "refactor(api): SuperUserController 를 AdminController 로 이동" -m "경로를 /api/super/** 에서 /api/admin/** 으로 바꾸고 메서드 매핑도
users, users/{id}/role 형태로 정리한다. 역할 이름 SUPER_USER 는 그대로 둔다 —
enum 값 변경은 토큰 claim 과 DB 값에 모두 영향을 주고 얻는 것이 없다."
```

---

## Task 2: 부서 API

**Files:**
- Create: `apps/api/src/main/java/com/example/bitcomputer/model/DeptCreateRequestDTO.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/exception/DuplicateDeptNameException.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/service/DeptService.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/serviceImpl/DeptServiceImpl.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/controller/DeptController.java`
- Create: `apps/api/src/main/java/com/example/bitcomputer/controller/AdminDeptController.java`
- Create: `apps/api/src/test/java/com/example/bitcomputer/controller/DeptControllerTest.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/GlobalExceptionHandler.java`

**Interfaces:**
- Consumes: Task 1의 `/api/admin` 경로 규약
- Produces:
  - `GET /api/depts` → `List<DeptDTO>`, `DeptDTO { int id; String dept; long employeeCount; }`
  - `POST /api/admin/depts` (body `{"dept":"내과"}`) → 201 + `DeptDTO`
  - `PUT /api/admin/depts/{id}` (body 동일) → 200 + `DeptDTO`
  - `DeptService.findAll()`, `create(String)`, `rename(int, String)`

- [ ] **Step 1: 기존 DeptDTO 확장**

`apps/api/src/main/java/com/example/bitcomputer/model/DeptDTO.java`가 이미 있으나 필드가 `id`, `dept` 둘뿐이고 생성자 애너테이션이 없다. 사용처는 없음을 확인했으므로 자유롭게 고친다.

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/model/DeptDTO.java <<'EOF'
package com.example.bitcomputer.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class DeptDTO {
    private int id;
    private String dept;
    /** 이 부서에 소속된 직원 수. 어느 부서가 실제로 쓰이는지 화면에서 보이게 한다. */
    private long employeeCount;
}
EOF
```

`@AllArgsConstructor`가 있어야 `new DeptDTO(id, dept, count)` 호출이 컴파일된다. 기존 코드가 `new DeptDTO()` 후 setter 를 쓰지 않으므로 `@NoArgsConstructor`는 Jackson 역직렬화용이다.

- [ ] **Step 2: 실패하는 테스트 작성**

```bash
cat > apps/api/src/test/java/com/example/bitcomputer/controller/DeptControllerTest.java <<'EOF'
package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.DeptRepository;
import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.config.TestRabbitConfig;
import com.example.bitcomputer.config.TestRedisConfig;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({TestRedisConfig.class, TestRabbitConfig.class})
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DeptControllerTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private JwtTokenProvider jwtTokenProvider;
    @Autowired private DeptRepository deptRepository;

    private jakarta.servlet.http.Cookie cookieFor(Role role) {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken("tester", role));
    }

    @Test
    void anyAuthenticatedRoleCanListDepts() throws Exception {
        mockMvc.perform(get("/api/depts").cookie(cookieFor(Role.RECEPTIONIST)))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$[0].dept").exists());
    }

    @Test
    void defaultRoleCannotListDepts() throws Exception {
        mockMvc.perform(get("/api/depts").cookie(cookieFor(Role.DEFAULT)))
               .andExpect(status().isForbidden());
    }

    @Test
    void superUserCanCreateDept() throws Exception {
        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"내과\"}"))
               .andExpect(status().isCreated())
               .andExpect(jsonPath("$.dept").value("내과"));
    }

    @Test
    void doctorCannotCreateDept() throws Exception {
        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.DOCTOR)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"외과\"}"))
               .andExpect(status().isForbidden());
    }

    @Test
    void duplicateDeptNameIsRejected() throws Exception {
        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"중복과\"}"))
               .andExpect(status().isCreated());

        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"중복과\"}"))
               .andExpect(status().isConflict());
    }

    @Test
    void blankDeptNameIsRejected() throws Exception {
        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"   \"}"))
               .andExpect(status().isBadRequest());
    }

    @Test
    void renamingUnknownDeptReturns404() throws Exception {
        mockMvc.perform(put("/api/admin/depts/99999")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"없는과\"}"))
               .andExpect(status().isNotFound());
    }

    @Test
    void deptListIncludesEmployeeCount() throws Exception {
        mockMvc.perform(get("/api/depts").cookie(cookieFor(Role.SUPER_USER)))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$[0].employeeCount").isNumber());
    }
}
EOF
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*DeptControllerTest*'
```

Expected: 전부 404 또는 컴파일 실패

- [ ] **Step 4: DTO와 예외 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/model/DeptCreateRequestDTO.java <<'EOF'
package com.example.bitcomputer.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class DeptCreateRequestDTO {
    private String dept;
}
EOF

cat > apps/api/src/main/java/com/example/bitcomputer/exception/DuplicateDeptNameException.java <<'EOF'
package com.example.bitcomputer.exception;

/** 이미 존재하는 부서명으로 생성·수정하려 할 때. 409 로 매핑된다. */
public class DuplicateDeptNameException extends RuntimeException {
    public DuplicateDeptNameException(String message) {
        super(message);
    }
}
EOF
```

- [ ] **Step 5: 서비스 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/service/DeptService.java <<'EOF'
package com.example.bitcomputer.service;

import com.example.bitcomputer.model.DeptDTO;

import java.util.List;

public interface DeptService {
    List<DeptDTO> findAll();
    DeptDTO create(String name);
    DeptDTO rename(int id, String name);
}
EOF

cat > apps/api/src/main/java/com/example/bitcomputer/serviceImpl/DeptServiceImpl.java <<'EOF'
package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.Repository.DeptRepository;
import com.example.bitcomputer.Repository.EmployeeRepository;
import com.example.bitcomputer.entity.Dept;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.exception.DuplicateDeptNameException;
import com.example.bitcomputer.model.DeptDTO;
import com.example.bitcomputer.service.DeptService;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class DeptServiceImpl implements DeptService {

    private final DeptRepository deptRepository;
    private final EmployeeRepository employeeRepository;

    public DeptServiceImpl(DeptRepository deptRepository, EmployeeRepository employeeRepository) {
        this.deptRepository = deptRepository;
        this.employeeRepository = employeeRepository;
    }

    @Override
    @Transactional(readOnly = true)
    public List<DeptDTO> findAll() {
        Map<Integer, Long> counts = employeeRepository.findAll().stream()
                .collect(Collectors.groupingBy(Employee::getDeptId, Collectors.counting()));

        return deptRepository.findAll().stream()
                .sorted(Comparator.comparingInt(Dept::getId))
                .map(d -> new DeptDTO(d.getId(), d.getDept(), counts.getOrDefault(d.getId(), 0L)))
                .collect(Collectors.toList());
    }

    @Override
    @Transactional
    public DeptDTO create(String name) {
        String trimmed = requireNonBlank(name);
        requireNameAvailable(trimmed, null);

        Dept saved = deptRepository.save(new Dept(0, trimmed));
        return new DeptDTO(saved.getId(), saved.getDept(), 0L);
    }

    @Override
    @Transactional
    public DeptDTO rename(int id, String name) {
        String trimmed = requireNonBlank(name);

        Dept dept = deptRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("부서를 찾을 수 없습니다. id=" + id));

        requireNameAvailable(trimmed, id);

        dept.setDept(trimmed);
        deptRepository.save(dept);

        long count = employeeRepository.findAll().stream()
                .filter(e -> e.getDeptId() == id)
                .count();
        return new DeptDTO(dept.getId(), dept.getDept(), count);
    }

    private String requireNonBlank(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("부서명은 비어 있을 수 없습니다.");
        }
        return name.trim();
    }

    /** excludeId 가 null 이 아니면 그 부서는 중복 검사에서 제외한다(자기 자신 이름 유지 허용). */
    private void requireNameAvailable(String name, Integer excludeId) {
        boolean taken = deptRepository.findAll().stream()
                .filter(d -> excludeId == null || d.getId() != excludeId)
                .anyMatch(d -> d.getDept().equalsIgnoreCase(name));
        if (taken) {
            throw new DuplicateDeptNameException("이미 존재하는 부서명입니다: " + name);
        }
    }
}
EOF
```

- [ ] **Step 6: 컨트롤러 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/controller/DeptController.java <<'EOF'
package com.example.bitcomputer.controller;

import com.example.bitcomputer.model.DeptDTO;
import com.example.bitcomputer.service.DeptService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 부서 목록 조회.
 *
 * SUPER_USER 전용인 /api/admin 밖에 두는 이유는 직원 추가 폼에서 부서를 고르려면
 * 목록이 필요하고, 부서명은 민감 정보가 아니기 때문이다. SecurityConfig 의
 * anyRequest() 규칙에 걸려 DEFAULT 를 제외한 인증된 역할이 읽을 수 있다.
 */
@RestController
@RequestMapping("/api/depts")
public class DeptController {

    private final DeptService deptService;

    public DeptController(DeptService deptService) {
        this.deptService = deptService;
    }

    @GetMapping
    public ResponseEntity<List<DeptDTO>> list() {
        return ResponseEntity.ok(deptService.findAll());
    }
}
EOF

cat > apps/api/src/main/java/com/example/bitcomputer/controller/AdminDeptController.java <<'EOF'
package com.example.bitcomputer.controller;

import com.example.bitcomputer.model.DeptCreateRequestDTO;
import com.example.bitcomputer.model.DeptDTO;
import com.example.bitcomputer.service.DeptService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 부서 생성·수정. SecurityConfig 에서 /api/admin/** 가 SUPER_USER 전용으로 묶여 있다. */
@RestController
@RequestMapping("/api/admin/depts")
public class AdminDeptController {

    private final DeptService deptService;

    public AdminDeptController(DeptService deptService) {
        this.deptService = deptService;
    }

    @PostMapping
    public ResponseEntity<DeptDTO> create(@RequestBody DeptCreateRequestDTO request) {
        DeptDTO created = deptService.create(request.getDept());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @PutMapping("/{id}")
    public ResponseEntity<DeptDTO> rename(@PathVariable int id,
                                          @RequestBody DeptCreateRequestDTO request) {
        return ResponseEntity.ok(deptService.rename(id, request.getDept()));
    }
}
EOF
```

- [ ] **Step 7: 예외 매핑 추가**

`GlobalExceptionHandler.java`에 두 핸들러를 추가한다. 기존 핸들러는 건드리지 않는다.

```java
    @ExceptionHandler(com.example.bitcomputer.exception.DuplicateDeptNameException.class)
    public ResponseEntity<String> handleDuplicateDeptName(
            com.example.bitcomputer.exception.DuplicateDeptNameException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(ex.getMessage());
    }

    @ExceptionHandler(jakarta.persistence.EntityNotFoundException.class)
    public ResponseEntity<String> handleEntityNotFound(jakarta.persistence.EntityNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ex.getMessage());
    }
```

`EntityNotFoundException` 핸들러가 이미 있으면 추가하지 않는다. 확인:

```bash
grep -n "EntityNotFoundException" apps/api/src/main/java/com/example/bitcomputer/GlobalExceptionHandler.java
```

- [ ] **Step 8: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*DeptControllerTest*'
```

Expected: 8개 PASS

- [ ] **Step 9: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/model/Dept*.java \
        apps/api/src/main/java/com/example/bitcomputer/exception/DuplicateDeptNameException.java \
        apps/api/src/main/java/com/example/bitcomputer/service/DeptService.java \
        apps/api/src/main/java/com/example/bitcomputer/serviceImpl/DeptServiceImpl.java \
        apps/api/src/main/java/com/example/bitcomputer/controller/DeptController.java \
        apps/api/src/main/java/com/example/bitcomputer/controller/AdminDeptController.java \
        apps/api/src/main/java/com/example/bitcomputer/GlobalExceptionHandler.java \
        apps/api/src/test/java/com/example/bitcomputer/controller/DeptControllerTest.java
git commit -m "feat(api): 부서 조회·생성·수정 API 추가" -m "부서를 늘릴 수단이 없어 전 직원이 UNASSIGNED 에 머물러 있었다.

목록 조회는 /api/depts 로 두어 DEFAULT 를 제외한 인증 역할이 읽을 수 있게 한다 —
직원 추가 폼에서 부서를 고르려면 필요하고 부서명은 민감 정보가 아니다.
생성·수정은 /api/admin/depts 로 SUPER_USER 에 한정한다.

삭제는 만들지 않는다. 직원이 참조 중인 부서를 지우면 FK 위반이며 그것이
회원가입 500 의 원인이었다."
```

---

## Task 3: 감사 로그 필터

**Files:**
- Create: `apps/api/src/main/java/com/example/bitcomputer/Repository/AuditLogSpecifications.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/Repository/AccessAuditLogRepository.java`
- Modify: `apps/api/src/main/java/com/example/bitcomputer/controller/AuditLogController.java`
- Create: `apps/api/src/test/java/com/example/bitcomputer/controller/AuditLogFilterTest.java`

**Interfaces:**
- Consumes: Task 1의 `/api/admin` 규약 (감사 API 경로는 `/api/audit`로 유지)
- Produces: `GET /api/audit/logs?page&size&actorUsername&targetPatientId&action&outcome&from&to` → `Page<AccessAuditLog>`

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
cat > apps/api/src/test/java/com/example/bitcomputer/controller/AuditLogFilterTest.java <<'EOF'
package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.config.TestRabbitConfig;
import com.example.bitcomputer.config.TestRedisConfig;
import com.example.bitcomputer.entity.AccessAuditLog;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDateTime;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({TestRedisConfig.class, TestRabbitConfig.class})
class AuditLogFilterTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private JwtTokenProvider jwtTokenProvider;
    @Autowired private AccessAuditLogRepository repository;

    private jakarta.servlet.http.Cookie adminCookie() {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken("admin", Role.SUPER_USER));
    }

    private AccessAuditLog row(String actor, String action, Integer patientId,
                               String outcome, LocalDateTime at) {
        AccessAuditLog log = new AccessAuditLog();
        log.setOccurredAt(at);
        log.setActorUsername(actor);
        log.setActorRole("DOCTOR");
        log.setAction(action);
        log.setTargetPatientId(patientId);
        log.setRequestIp("127.0.0.1");
        log.setOutcome(outcome);
        return log;
    }

    @BeforeEach
    void seed() {
        repository.deleteAll();
        repository.save(row("dr.kim", "PATIENT_VIEW", 1, "GRANTED",
                LocalDateTime.of(2026, 1, 1, 10, 0)));
        repository.save(row("dr.lee", "PATIENT_VIEW", 2, "GRANTED",
                LocalDateTime.of(2026, 2, 1, 10, 0)));
        repository.save(row("front.park", "ACCESS_DENIED", null, "DENIED",
                LocalDateTime.of(2026, 3, 1, 10, 0)));
    }

    @Test
    void noFilterReturnsAll() throws Exception {
        mockMvc.perform(get("/api/audit/logs").cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.totalElements").value(3));
    }

    @Test
    void filtersByActorUsernamePartialMatch() throws Exception {
        mockMvc.perform(get("/api/audit/logs?actorUsername=dr.").cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void filtersByTargetPatientId() throws Exception {
        mockMvc.perform(get("/api/audit/logs?targetPatientId=2").cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.totalElements").value(1))
               .andExpect(jsonPath("$.content[0].actorUsername").value("dr.lee"));
    }

    @Test
    void filtersByOutcome() throws Exception {
        mockMvc.perform(get("/api/audit/logs?outcome=DENIED").cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.totalElements").value(1))
               .andExpect(jsonPath("$.content[0].actorUsername").value("front.park"));
    }

    @Test
    void filtersByAction() throws Exception {
        mockMvc.perform(get("/api/audit/logs?action=PATIENT_VIEW").cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.totalElements").value(2));
    }

    @Test
    void filtersByDateRange() throws Exception {
        mockMvc.perform(get("/api/audit/logs?from=2026-01-15T00:00:00&to=2026-02-15T00:00:00")
                       .cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.totalElements").value(1))
               .andExpect(jsonPath("$.content[0].actorUsername").value("dr.lee"));
    }

    @Test
    void combinesFilters() throws Exception {
        mockMvc.perform(get("/api/audit/logs?action=PATIENT_VIEW&outcome=GRANTED&actorUsername=kim")
                       .cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.totalElements").value(1))
               .andExpect(jsonPath("$.content[0].actorUsername").value("dr.kim"));
    }

    @Test
    void resultsAreNewestFirst() throws Exception {
        mockMvc.perform(get("/api/audit/logs").cookie(adminCookie()))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$.content[0].actorUsername").value("front.park"));
    }
}
EOF
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*AuditLogFilterTest*'
```

Expected: 필터 테스트들이 `totalElements`가 3으로 나와 실패 (필터가 무시됨)

- [ ] **Step 3: Repository에 Specification 지원 추가**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/Repository/AccessAuditLogRepository.java <<'EOF'
package com.example.bitcomputer.Repository;

import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface AccessAuditLogRepository
        extends JpaRepository<AccessAuditLog, Long>, JpaSpecificationExecutor<AccessAuditLog> {
    Page<AccessAuditLog> findAllByOrderByOccurredAtDesc(Pageable pageable);
}
EOF
```

- [ ] **Step 4: Specification 작성**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/Repository/AuditLogSpecifications.java <<'EOF'
package com.example.bitcomputer.Repository;

import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.jpa.domain.Specification;

import java.time.LocalDateTime;

/**
 * 감사 로그 필터 조합.
 *
 * 파라미터가 6개이고 조합이 자유로워 메서드 이름 기반 쿼리로는 감당되지 않는다.
 * 각 메서드는 값이 없으면 null 을 반환하고, and() 가 null 을 무시한다.
 */
public final class AuditLogSpecifications {

    private AuditLogSpecifications() {
    }

    public static Specification<AccessAuditLog> actorUsernameContains(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String pattern = "%" + value.trim().toLowerCase() + "%";
        return (root, query, cb) -> cb.like(cb.lower(root.get("actorUsername")), pattern);
    }

    public static Specification<AccessAuditLog> targetPatientIdEquals(Integer value) {
        if (value == null) {
            return null;
        }
        return (root, query, cb) -> cb.equal(root.get("targetPatientId"), value);
    }

    public static Specification<AccessAuditLog> actionEquals(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return (root, query, cb) -> cb.equal(root.get("action"), value.trim());
    }

    public static Specification<AccessAuditLog> outcomeEquals(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return (root, query, cb) -> cb.equal(root.get("outcome"), value.trim());
    }

    public static Specification<AccessAuditLog> occurredFrom(LocalDateTime value) {
        if (value == null) {
            return null;
        }
        return (root, query, cb) -> cb.greaterThanOrEqualTo(root.get("occurredAt"), value);
    }

    public static Specification<AccessAuditLog> occurredTo(LocalDateTime value) {
        if (value == null) {
            return null;
        }
        return (root, query, cb) -> cb.lessThanOrEqualTo(root.get("occurredAt"), value);
    }
}
EOF
```

- [ ] **Step 5: 컨트롤러 수정**

```bash
cat > apps/api/src/main/java/com/example/bitcomputer/controller/AuditLogController.java <<'EOF'
package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.Repository.AuditLogSpecifications;
import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;

/**
 * 감사 로그 조회. SecurityConfig 에서 SUPER_USER 전용으로 묶여 있다.
 *
 * 이 엔드포인트에는 @AuditPatientAccess 를 붙이지 않는다. 감사 로그 조회를 감사 로그에
 * 남기면 조회할 때마다 행이 늘어 신호 대 잡음비가 나빠진다.
 */
@RestController
@RequestMapping("/api/audit")
public class AuditLogController {

    private final AccessAuditLogRepository repository;

    public AuditLogController(AccessAuditLogRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/logs")
    public ResponseEntity<Page<AccessAuditLog>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size,
            @RequestParam(required = false) String actorUsername,
            @RequestParam(required = false) Integer targetPatientId,
            @RequestParam(required = false) String action,
            @RequestParam(required = false) String outcome,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to) {

        Specification<AccessAuditLog> spec = Specification
                .allOf(AuditLogSpecifications.actorUsernameContains(actorUsername),
                       AuditLogSpecifications.targetPatientIdEquals(targetPatientId),
                       AuditLogSpecifications.actionEquals(action),
                       AuditLogSpecifications.outcomeEquals(outcome),
                       AuditLogSpecifications.occurredFrom(from),
                       AuditLogSpecifications.occurredTo(to));

        PageRequest pageable = PageRequest.of(
                page, Math.min(size, 200), Sort.by(Sort.Direction.DESC, "occurredAt"));

        return ResponseEntity.ok(repository.findAll(spec, pageable));
    }
}
EOF
```

`Specification.allOf`는 Spring Data JPA 3.x의 API다. 컴파일 오류가 나면 이 프로젝트의 버전이 다른 것이므로 아래로 대체한다.

```java
        Specification<AccessAuditLog> spec = Specification.where(
                AuditLogSpecifications.actorUsernameContains(actorUsername))
                .and(AuditLogSpecifications.targetPatientIdEquals(targetPatientId))
                .and(AuditLogSpecifications.actionEquals(action))
                .and(AuditLogSpecifications.outcomeEquals(outcome))
                .and(AuditLogSpecifications.occurredFrom(from))
                .and(AuditLogSpecifications.occurredTo(to));
```

어느 쪽을 썼는지 보고한다.

- [ ] **Step 6: 테스트가 통과하는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*AuditLogFilterTest*'
```

Expected: 8개 PASS

- [ ] **Step 7: 기존 감사 테스트가 깨지지 않았는지 확인**

```bash
cd apps/api && ./gradlew test --tests '*AuditLogTest*' --tests '*AuditFailureToleranceTest*'
```

Expected: 전부 PASS. `findAllByOrderByOccurredAtDesc`를 남겨뒀으므로 기존 호출부는 영향받지 않는다.

- [ ] **Step 8: 커밋**

```bash
git add apps/api/src/main/java/com/example/bitcomputer/Repository/AccessAuditLogRepository.java \
        apps/api/src/main/java/com/example/bitcomputer/Repository/AuditLogSpecifications.java \
        apps/api/src/main/java/com/example/bitcomputer/controller/AuditLogController.java \
        apps/api/src/test/java/com/example/bitcomputer/controller/AuditLogFilterTest.java
git commit -m "feat(api): 감사 로그 조회에 필터 파라미터 추가" -m "행위자(부분 일치), 대상 환자, 행위 종류, 결과, 기간으로 걸러 볼 수 있게 한다.
파라미터가 6개이고 조합이 자유로워 JpaSpecificationExecutor 로 구성했다.
정렬은 occurredAt 내림차순 고정 — 다른 순서로 볼 상황이 떠오르지 않아
정렬 파라미터를 만들지 않았다."
```

---

## Task 4: 프론트 `/admin` 레이아웃과 API 클라이언트

**Files:**
- Create: `apps/web/src/types/dept.ts`
- Create: `apps/web/src/types/audit.ts`
- Create: `apps/web/src/services/admin.ts`
- Create: `apps/web/src/app/(auth)/admin/layout.tsx`
- Create: `apps/web/src/app/(auth)/admin/layout.module.css`
- Create: `apps/web/src/app/(auth)/admin/page.tsx`
- Move: `apps/web/src/app/(auth)/super/page.tsx` → `apps/web/src/app/(auth)/admin/users/page.tsx`
- Move: `apps/web/src/app/(auth)/super/page.module.css` → `apps/web/src/app/(auth)/admin/users/page.module.css`
- Delete: `apps/web/src/services/super.ts`

**Interfaces:**
- Consumes: Task 1의 `/api/admin/users`, Task 2의 `/api/depts`·`/api/admin/depts`, Task 3의 감사 필터 파라미터
- Produces:
  - `types/dept.ts`: `Dept { id: number; dept: string; employeeCount: number }`
  - `types/audit.ts`: `AuditLog { id, occurredAt, actorUsername, actorRole, action, targetPatientId, targetHistoryId, requestIp, outcome, detail }`, `AuditFilter`, `Page<T>`
  - `services/admin.ts`: `getAllUsers`, `createUser`, `setRole`, `getDepts`, `createDept`, `renameDept`, `getAuditLogs`

- [ ] **Step 1: 타입 정의**

```bash
cat > apps/web/src/types/dept.ts <<'EOF'
export interface Dept {
  id: number;
  dept: string;
  employeeCount: number;
}
EOF

cat > apps/web/src/types/audit.ts <<'EOF'
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
EOF
```

- [ ] **Step 2: API 클라이언트 작성**

```bash
cat > apps/web/src/services/admin.ts <<'EOF'
import { get, post, put } from "./http/client";
import { Role, User } from "@/types/user";
import { Dept } from "@/types/dept";
import { AuditFilter, AuditLog, Page } from "@/types/audit";

interface GetAllUsersResponseBody {
  totalUserCount: number;
  users: User[];
}

export interface CreateUserRequestBody {
  name: string;
  deptId: number;
  role: Role;
  username: string;
  password: string;
}

export async function getAllUsers(): Promise<GetAllUsersResponseBody | User[]> {
  return get<GetAllUsersResponseBody | User[]>("/api/admin/users");
}

export async function createUser(body: CreateUserRequestBody): Promise<void> {
  await post<void, CreateUserRequestBody>("/api/admin/users", body);
}

export async function setRole(id: number, role: Role): Promise<void> {
  await put<void, { role: Role }>(`/api/admin/users/${id}/role`, { role });
}

export async function getDepts(): Promise<Dept[]> {
  return get<Dept[]>("/api/depts");
}

export async function createDept(dept: string): Promise<Dept> {
  return post<Dept, { dept: string }>("/api/admin/depts", { dept });
}

export async function renameDept(id: number, dept: string): Promise<Dept> {
  return put<Dept, { dept: string }>(`/api/admin/depts/${id}`, { dept });
}

export async function getAuditLogs(filter: AuditFilter): Promise<Page<AuditLog>> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filter)) {
    if (value !== undefined && value !== null && value !== "") {
      params.append(key, String(value));
    }
  }
  const qs = params.toString();
  return get<Page<AuditLog>>(`/api/audit/logs${qs ? `?${qs}` : ""}`);
}
EOF
```

- [ ] **Step 3: 레이아웃 작성**

```bash
mkdir -p "apps/web/src/app/(auth)/admin"
cat > "apps/web/src/app/(auth)/admin/layout.module.css" <<'EOF'
.shell {
  display: grid;
  grid-template-columns: 200px 1fr;
  min-height: 100vh;
}

.sidebar {
  border-right: 1px solid #e5e5e5;
  padding: 24px 16px;
  background: #fafafa;
}

.title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 20px;
}

.navLink {
  display: block;
  padding: 8px 12px;
  border-radius: 6px;
  color: #333;
  text-decoration: none;
  font-size: 14px;
  margin-bottom: 4px;
}

.navLink:hover {
  background: #eee;
}

.navLinkActive {
  background: #1a4f8a;
  color: #fff;
}

.content {
  padding: 24px 32px;
  overflow-x: auto;
}

.gate {
  padding: 48px;
  text-align: center;
  color: #666;
}
EOF

cat > "apps/web/src/app/(auth)/admin/layout.tsx" <<'EOF'
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getRole } from "@/services/auth";
import { Role } from "@/types/user";
import styles from "./layout.module.css";

const NAV = [
  { href: "/admin/audit", label: "감사 로그" },
  { href: "/admin/depts", label: "부서 관리" },
  { href: "/admin/users", label: "직원 관리" },
];

/**
 * 관리자 콘솔 공통 레이아웃.
 *
 * 역할 확인을 여기서 한 번만 하고 하위 화면은 반복하지 않는다.
 * 이것은 UX 장치이며 방어 계층이 아니다 — 실제 권한 판정은 서버가 하고,
 * SUPER_USER 가 아니면 /api/admin/** 이 403 을 반환한다.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    getRole()
      .then((role) => setAllowed(role === Role.SUPER_USER))
      .catch(() => setAllowed(false));
  }, []);

  if (allowed === null) {
    return <div className={styles.gate}>확인 중…</div>;
  }

  if (!allowed) {
    return <div className={styles.gate}>관리자만 접근할 수 있습니다.</div>;
  }

  return (
    <div className={styles.shell}>
      <nav className={styles.sidebar}>
        <h1 className={styles.title}>관리자 콘솔</h1>
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={
              pathname === item.href
                ? `${styles.navLink} ${styles.navLinkActive}`
                : styles.navLink
            }
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <main className={styles.content}>{children}</main>
    </div>
  );
}
EOF

cat > "apps/web/src/app/(auth)/admin/page.tsx" <<'EOF'
import { redirect } from "next/navigation";

export default function AdminIndexPage() {
  redirect("/admin/audit");
}
EOF
```

- [ ] **Step 4: 기존 직원 화면 이관**

```bash
mkdir -p "apps/web/src/app/(auth)/admin/users"
git mv "apps/web/src/app/(auth)/super/page.tsx" "apps/web/src/app/(auth)/admin/users/page.tsx"
git mv "apps/web/src/app/(auth)/super/page.module.css" "apps/web/src/app/(auth)/admin/users/page.module.css"
rmdir "apps/web/src/app/(auth)/super" 2>/dev/null || true
git rm -q apps/web/src/services/super.ts
```

`apps/web/src/app/(auth)/admin/users/page.tsx`에서 import와 컴포넌트 이름을 바꾼다.

```tsx
import { createUser, getAllUsers, setRole } from "@/services/admin";
```

```tsx
export default function AdminUsersPage() {
```

`setRole` 호출부의 시그니처가 바뀌었다. 기존은 `setRole({ id, role })`, 새 것은 `setRole(id, role)`이다. 호출부를 찾아 고친다.

```bash
grep -n "setRole(" "apps/web/src/app/(auth)/admin/users/page.tsx"
```

- [ ] **Step 5: 잔존 참조 확인**

```bash
grep -rn "services/super\|/super\b\|api/super" apps/web/src | grep -v node_modules
```

Expected: 출력 없음

- [ ] **Step 6: 타입 체크와 빌드**

```bash
cd apps/web && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/next build 2>&1 | tail -5
```

Expected: 타입 오류 없음, 빌드 성공

- [ ] **Step 7: 커밋**

```bash
git add -A apps/web/src
git commit -m "refactor(web): 관리자 화면을 /admin 중첩 라우트로 재편" -m "layout.tsx 에서 역할을 한 번만 확인하고 하위 화면은 반복하지 않는다.
기존 /super 의 직원 관리 기능은 /admin/users 로 옮기기만 하고 기능은 그대로다.

services/super.ts 를 services/admin.ts 로 대체하며 부서·감사 API 를 함께 넣었다.
setRole 시그니처를 setRole(id, role) 로 바꿔 객체 래핑을 없앴다."
```

---

## Task 5: 부서 관리 화면과 직원 추가 폼 select 전환

**Files:**
- Create: `apps/web/src/app/(auth)/admin/depts/page.tsx`
- Create: `apps/web/src/app/(auth)/admin/depts/page.module.css`
- Create: `apps/web/src/app/(auth)/admin/depts/__tests__/page.test.tsx`
- Modify: `apps/web/src/app/(auth)/admin/users/page.tsx`

**Interfaces:**
- Consumes: Task 4의 `getDepts`, `createDept`, `renameDept`, `Dept` 타입
- Produces: 없음 (화면)

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
mkdir -p "apps/web/src/app/(auth)/admin/depts/__tests__"
cat > "apps/web/src/app/(auth)/admin/depts/__tests__/page.test.tsx" <<'EOF'
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DeptsPage from "../page";

vi.mock("@/services/admin", () => ({
  getDepts: vi.fn(),
  createDept: vi.fn(),
  renameDept: vi.fn(),
}));

import { createDept, getDepts } from "@/services/admin";

describe("부서 관리 화면", () => {
  beforeEach(() => {
    vi.mocked(getDepts).mockResolvedValue([
      { id: 1, dept: "UNASSIGNED", employeeCount: 16 },
      { id: 2, dept: "내과", employeeCount: 0 },
    ]);
    vi.mocked(createDept).mockResolvedValue({ id: 3, dept: "외과", employeeCount: 0 });
  });

  it("부서 목록과 소속 인원을 표시한다", async () => {
    render(<DeptsPage />);
    expect(await screen.findByText("UNASSIGNED")).toBeTruthy();
    expect(await screen.findByText("내과")).toBeTruthy();
    expect(await screen.findByText("16")).toBeTruthy();
  });

  it("부서를 추가하면 API 를 호출한다", async () => {
    const user = userEvent.setup();
    render(<DeptsPage />);
    await screen.findByText("UNASSIGNED");

    await user.type(screen.getByLabelText("새 부서명"), "외과");
    await user.click(screen.getByRole("button", { name: "추가" }));

    await waitFor(() => expect(createDept).toHaveBeenCalledWith("외과"));
  });

  it("빈 이름으로는 추가 버튼이 동작하지 않는다", async () => {
    const user = userEvent.setup();
    render(<DeptsPage />);
    await screen.findByText("UNASSIGNED");

    await user.click(screen.getByRole("button", { name: "추가" }));
    expect(createDept).not.toHaveBeenCalled();
  });
});
EOF
```

`@testing-library/user-event`가 설치돼 있지 않으면 추가한다.

```bash
cd apps/web && node .yarn/releases/yarn-4.12.0.cjs add -D @testing-library/user-event
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/web && ./node_modules/.bin/vitest run src/app/\(auth\)/admin/depts
```

Expected: FAIL — `../page` 모듈 없음

- [ ] **Step 3: 화면 구현**

```bash
cat > "apps/web/src/app/(auth)/admin/depts/page.module.css" <<'EOF'
.header { font-size: 20px; font-weight: 600; margin: 0 0 20px; }
.addForm { display: flex; gap: 8px; align-items: flex-end; margin-bottom: 24px; }
.field { display: grid; gap: 6px; }
.label { font-size: 13px; color: #555; }
.input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; }
.button { padding: 8px 16px; border: 0; border-radius: 6px; background: #1a4f8a; color: #fff; cursor: pointer; }
.button:disabled { background: #aaa; cursor: not-allowed; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #eee; font-size: 14px; }
.error { color: #c00; margin-bottom: 12px; }
.success { color: #067; margin-bottom: 12px; }
EOF

cat > "apps/web/src/app/(auth)/admin/depts/page.tsx" <<'EOF'
"use client";

import { useEffect, useState } from "react";
import { createDept, getDepts, renameDept } from "@/services/admin";
import { Dept } from "@/types/dept";
import styles from "./page.module.css";

export default function DeptsPage() {
  const [depts, setDepts] = useState<Dept[]>([]);
  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      setDepts(await getDepts());
    } catch (err) {
      setError(err instanceof Error ? err.message : "부서 목록을 불러오지 못했습니다");
    }
  }

  async function handleAdd() {
    if (!newName.trim()) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await createDept(newName.trim());
      setNewName("");
      setMessage("부서를 추가했습니다");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "부서 추가에 실패했습니다");
    } finally {
      setBusy(false);
    }
  }

  async function handleRename(id: number) {
    if (!editingName.trim()) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await renameDept(id, editingName.trim());
      setEditingId(null);
      setMessage("부서명을 변경했습니다");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "부서명 변경에 실패했습니다");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2 className={styles.header}>부서 관리</h2>

      {error && <p className={styles.error}>{error}</p>}
      {message && <p className={styles.success}>{message}</p>}

      <div className={styles.addForm}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="new-dept">새 부서명</label>
          <input
            id="new-dept"
            className={styles.input}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="내과"
          />
        </div>
        <button className={styles.button} onClick={handleAdd} disabled={busy}>
          추가
        </button>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>ID</th>
            <th>부서명</th>
            <th>소속 인원</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {depts.map((d) => (
            <tr key={d.id}>
              <td>{d.id}</td>
              <td>
                {editingId === d.id ? (
                  <input
                    className={styles.input}
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    aria-label={`${d.dept} 이름 수정`}
                  />
                ) : (
                  d.dept
                )}
              </td>
              <td>{d.employeeCount}</td>
              <td>
                {editingId === d.id ? (
                  <button
                    className={styles.button}
                    onClick={() => handleRename(d.id)}
                    disabled={busy}
                  >
                    저장
                  </button>
                ) : (
                  <button
                    className={styles.button}
                    onClick={() => {
                      setEditingId(d.id);
                      setEditingName(d.dept);
                    }}
                  >
                    이름 수정
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
EOF
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd apps/web && ./node_modules/.bin/vitest run src/app/\(auth\)/admin/depts
```

Expected: 3개 PASS

- [ ] **Step 5: 직원 추가 폼의 부서를 select 로 전환**

`apps/web/src/app/(auth)/admin/users/page.tsx`에서 `deptId` 입력을 찾는다.

```bash
grep -n "deptId" "apps/web/src/app/(auth)/admin/users/page.tsx"
```

import에 `getDepts`와 `Dept`를 추가하고, 부서 목록 state와 로딩을 넣는다.

```tsx
import { createUser, getAllUsers, getDepts, setRole } from "@/services/admin";
import { Dept } from "@/types/dept";
```

```tsx
  const [depts, setDepts] = useState<Dept[]>([]);

  useEffect(() => {
    getDepts().then(setDepts).catch(() => setDepts([]));
  }, []);
```

`deptId` 텍스트 입력을 select로 교체한다. 기존 입력의 className은 그대로 재사용한다.

```tsx
<select
  value={newUser.deptId}
  onChange={(e) => setNewUser({ ...newUser, deptId: e.target.value })}
  aria-label="부서"
>
  {depts.map((d) => (
    <option key={d.id} value={String(d.id)}>
      {d.dept}
    </option>
  ))}
</select>
```

`createUser` 호출부에서 `deptId`를 숫자로 변환하는지 확인한다. `CreateUserRequestBody.deptId`는 `number`다.

```bash
grep -n "createUser(" "apps/web/src/app/(auth)/admin/users/page.tsx"
```

- [ ] **Step 6: 타입 체크와 빌드**

```bash
cd apps/web && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vitest run && ./node_modules/.bin/next build 2>&1 | tail -3
```

Expected: 타입 오류 없음, 기존 3개 + 새 3개 테스트 통과, 빌드 성공

- [ ] **Step 7: 커밋**

```bash
git add -A apps/web/src
git commit -m "feat(web): 부서 관리 화면 추가와 직원 추가 폼 select 전환" -m "부서 목록·추가·이름 수정을 화면에서 할 수 있게 한다. 각 부서의 소속 인원을
함께 표시해 어느 부서가 실제로 쓰이는지 보이게 했다.

직원 추가 폼의 부서를 자유 입력에서 select 로 바꿨다. 존재하지 않는 부서
번호를 넣어 500 을 내던 경로가 화면에서 사라진다.

삭제 버튼은 만들지 않았다 — 직원이 참조 중인 부서를 지우면 FK 위반이다."
```

---

## Task 6: 감사 로그 화면

**Files:**
- Create: `apps/web/src/app/(auth)/admin/audit/page.tsx`
- Create: `apps/web/src/app/(auth)/admin/audit/page.module.css`
- Create: `apps/web/src/app/(auth)/admin/audit/__tests__/page.test.tsx`

**Interfaces:**
- Consumes: Task 4의 `getAuditLogs`, `AuditLog`, `AuditFilter`, `Page` 타입
- Produces: 없음 (화면)

- [ ] **Step 1: 실패하는 테스트 작성**

```bash
mkdir -p "apps/web/src/app/(auth)/admin/audit/__tests__"
cat > "apps/web/src/app/(auth)/admin/audit/__tests__/page.test.tsx" <<'EOF'
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuditPage from "../page";

vi.mock("@/services/admin", () => ({
  getAuditLogs: vi.fn(),
}));

import { getAuditLogs } from "@/services/admin";

const page = {
  content: [
    {
      id: 2, occurredAt: "2026-03-01T10:00:00", actorUsername: "front.park",
      actorRole: "RECEPTIONIST", action: "ACCESS_DENIED", targetPatientId: null,
      targetHistoryId: null, requestIp: "172.19.0.1", outcome: "DENIED",
      detail: "POST /api/agent/prescription/recommend",
    },
    {
      id: 1, occurredAt: "2026-01-01T10:00:00", actorUsername: "dr.kim",
      actorRole: "DOCTOR", action: "PATIENT_VIEW", targetPatientId: 1,
      targetHistoryId: null, requestIp: "172.19.0.1", outcome: "GRANTED",
      detail: "GET /api/patients/1",
    },
  ],
  totalElements: 2, totalPages: 1, number: 0, size: 50,
};

describe("감사 로그 화면", () => {
  beforeEach(() => {
    vi.mocked(getAuditLogs).mockResolvedValue(page);
  });

  it("로그 행을 표시한다", async () => {
    render(<AuditPage />);
    expect(await screen.findByText("dr.kim")).toBeTruthy();
    expect(await screen.findByText("front.park")).toBeTruthy();
  });

  it("초기 조회는 필터 없이 최신순 50건", async () => {
    render(<AuditPage />);
    await waitFor(() =>
      expect(getAuditLogs).toHaveBeenCalledWith({ page: 0, size: 50 })
    );
  });

  it("필터를 적용하면 파라미터가 전달된다", async () => {
    const user = userEvent.setup();
    render(<AuditPage />);
    await screen.findByText("dr.kim");

    await user.type(screen.getByLabelText("행위자"), "dr.");
    await user.selectOptions(screen.getByLabelText("결과"), "DENIED");
    await user.click(screen.getByRole("button", { name: "조회" }));

    await waitFor(() =>
      expect(getAuditLogs).toHaveBeenLastCalledWith(
        expect.objectContaining({ actorUsername: "dr.", outcome: "DENIED", page: 0 })
      )
    );
  });

  it("거부된 행에 구분 클래스를 붙인다", async () => {
    render(<AuditPage />);
    const denied = await screen.findByText("DENIED");
    expect(denied.closest("tr")?.className).toContain("denied");
  });
});
EOF
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

```bash
cd apps/web && ./node_modules/.bin/vitest run src/app/\(auth\)/admin/audit
```

Expected: FAIL — `../page` 모듈 없음

- [ ] **Step 3: 화면 구현**

```bash
cat > "apps/web/src/app/(auth)/admin/audit/page.module.css" <<'EOF'
.header { font-size: 20px; font-weight: 600; margin: 0 0 20px; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-bottom: 20px; padding: 16px; background: #fafafa; border-radius: 8px; }
.field { display: grid; gap: 6px; }
.label { font-size: 12px; color: #555; }
.input, .select { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
.button { padding: 7px 16px; border: 0; border-radius: 6px; background: #1a4f8a; color: #fff; cursor: pointer; }
.button:disabled { background: #aaa; cursor: not-allowed; }
.table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table th, .table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #eee; white-space: nowrap; }
.table td.detail { white-space: normal; color: #666; }
.denied { background: #fff4f4; }
.rejected { background: #fffaf0; }
.pager { display: flex; gap: 12px; align-items: center; margin-top: 16px; font-size: 13px; }
.error { color: #c00; margin-bottom: 12px; }
.empty { padding: 32px; text-align: center; color: #888; }
EOF

cat > "apps/web/src/app/(auth)/admin/audit/page.tsx" <<'EOF'
"use client";

import { useCallback, useEffect, useState } from "react";
import { getAuditLogs } from "@/services/admin";
import { AuditFilter, AuditLog, Page } from "@/types/audit";
import styles from "./page.module.css";

const PAGE_SIZE = 50;

const OUTCOMES = ["", "GRANTED", "DENIED", "CSRF_REJECTED"];

function rowClass(outcome: string): string {
  if (outcome === "DENIED") return styles.denied;
  if (outcome === "CSRF_REJECTED") return styles.rejected;
  return "";
}

export default function AuditPage() {
  const [result, setResult] = useState<Page<AuditLog> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [actorUsername, setActorUsername] = useState("");
  const [targetPatientId, setTargetPatientId] = useState("");
  const [action, setAction] = useState("");
  const [outcome, setOutcome] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const load = useCallback(async (page: number, filter: Omit<AuditFilter, "page" | "size">) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await getAuditLogs({ ...filter, page, size: PAGE_SIZE }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "감사 로그를 불러오지 못했습니다");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    load(0, {});
  }, [load]);

  function currentFilter(): Omit<AuditFilter, "page" | "size"> {
    const f: Omit<AuditFilter, "page" | "size"> = {};
    if (actorUsername.trim()) f.actorUsername = actorUsername.trim();
    if (targetPatientId.trim()) f.targetPatientId = Number(targetPatientId);
    if (action.trim()) f.action = action.trim();
    if (outcome) f.outcome = outcome;
    if (from) f.from = `${from}T00:00:00`;
    if (to) f.to = `${to}T23:59:59`;
    return f;
  }

  return (
    <div>
      <h2 className={styles.header}>감사 로그</h2>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.filters}>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="f-actor">행위자</label>
          <input id="f-actor" className={styles.input} value={actorUsername}
                 onChange={(e) => setActorUsername(e.target.value)} placeholder="계정 일부" />
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="f-patient">환자 ID</label>
          <input id="f-patient" className={styles.input} value={targetPatientId}
                 onChange={(e) => setTargetPatientId(e.target.value)} inputMode="numeric" />
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="f-action">행위</label>
          <input id="f-action" className={styles.input} value={action}
                 onChange={(e) => setAction(e.target.value)} placeholder="PATIENT_VIEW" />
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="f-outcome">결과</label>
          <select id="f-outcome" className={styles.select} value={outcome}
                  onChange={(e) => setOutcome(e.target.value)}>
            {OUTCOMES.map((o) => (
              <option key={o} value={o}>{o || "전체"}</option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="f-from">시작일</label>
          <input id="f-from" type="date" className={styles.input} value={from}
                 onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className={styles.field}>
          <label className={styles.label} htmlFor="f-to">종료일</label>
          <input id="f-to" type="date" className={styles.input} value={to}
                 onChange={(e) => setTo(e.target.value)} />
        </div>
        <button className={styles.button} disabled={busy}
                onClick={() => load(0, currentFilter())}>
          조회
        </button>
      </div>

      {result && result.content.length === 0 ? (
        <p className={styles.empty}>조건에 맞는 기록이 없습니다.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>시각</th><th>행위자</th><th>역할</th><th>행위</th>
              <th>환자</th><th>결과</th><th>IP</th><th>상세</th>
            </tr>
          </thead>
          <tbody>
            {result?.content.map((log) => (
              <tr key={log.id} className={rowClass(log.outcome)}>
                <td>{log.occurredAt.replace("T", " ").slice(0, 19)}</td>
                <td>{log.actorUsername}</td>
                <td>{log.actorRole}</td>
                <td>{log.action}</td>
                <td>{log.targetPatientId ?? "-"}</td>
                <td>{log.outcome}</td>
                <td>{log.requestIp ?? "-"}</td>
                <td className={styles.detail}>{log.detail ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {result && result.totalPages > 1 && (
        <div className={styles.pager}>
          <button className={styles.button} disabled={busy || result.number === 0}
                  onClick={() => load(result.number - 1, currentFilter())}>
            이전
          </button>
          <span>{result.number + 1} / {result.totalPages} (총 {result.totalElements}건)</span>
          <button className={styles.button}
                  disabled={busy || result.number >= result.totalPages - 1}
                  onClick={() => load(result.number + 1, currentFilter())}>
            다음
          </button>
        </div>
      )}
    </div>
  );
}
EOF
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd apps/web && ./node_modules/.bin/vitest run src/app/\(auth\)/admin/audit
```

Expected: 4개 PASS

- [ ] **Step 5: 전체 프론트 검증**

```bash
cd apps/web && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vitest run && ./node_modules/.bin/next build 2>&1 | tail -3
```

Expected: 타입 오류 없음, 전체 테스트 통과, 빌드 성공

- [ ] **Step 6: 커밋**

```bash
git add -A apps/web/src
git commit -m "feat(web): 감사 로그 조회 화면 추가" -m "행위자·환자·행위·결과·기간으로 걸러 볼 수 있다. DENIED 와 CSRF_REJECTED 행은
배경색으로 구분한다 — 이 화면을 여는 주된 이유가 거부된 시도를 찾는 것이기 때문이다.

RBAC 과 감사 로그를 Phase A 에서 만들었으나 그 결과를 볼 수단이 없었다."
```

---

## Task 7: E2E 시나리오 추가

**Files:**
- Modify: `tests/e2e/test_core_flow.py`

**Interfaces:**
- Consumes: Task 2의 부서 API, Task 3의 감사 필터, Task 1의 `/api/admin/users`
- Produces: 없음

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/e2e/test_core_flow.py` 끝에 추가한다. 기존 파일의 `csrf_headers` import와 픽스처를 그대로 쓴다.

```python
def test_admin_can_create_dept_and_see_it_in_list(super_user: httpx.Client):
    """부서를 만들고 목록에서 확인한다."""
    name = "E2E진료과"

    created = super_user.post(
        "/api/admin/depts",
        headers=csrf_headers(super_user),
        json={"dept": name},
    )
    # 이미 있으면 409 — 재실행 가능해야 하므로 둘 다 허용한다
    assert created.status_code in (201, 409), created.text

    listed = super_user.get("/api/depts")
    assert listed.status_code == 200
    assert any(d["dept"] == name for d in listed.json())


def test_duplicate_dept_name_is_rejected(super_user: httpx.Client):
    name = "E2E중복과"
    super_user.post("/api/admin/depts", headers=csrf_headers(super_user), json={"dept": name})

    again = super_user.post(
        "/api/admin/depts",
        headers=csrf_headers(super_user),
        json={"dept": name},
    )
    assert again.status_code == 409


def test_doctor_cannot_create_dept(doctor: httpx.Client):
    response = doctor.post(
        "/api/admin/depts",
        headers=csrf_headers(doctor),
        json={"dept": "의사가만든과"},
    )
    assert response.status_code == 403


def test_audit_log_filters_narrow_results(super_user: httpx.Client, patient_id: int):
    """환자 조회 후, 그 행위가 필터로 찾아지는지 확인한다."""
    super_user.get(f"/api/patients/{patient_id}")

    filtered = super_user.get(
        "/api/audit/logs",
        params={"action": "PATIENT_VIEW", "targetPatientId": patient_id, "size": 50},
    )
    assert filtered.status_code == 200

    rows = filtered.json()["content"]
    assert rows, "필터로 조회한 감사 기록이 비어 있다"
    assert all(r["action"] == "PATIENT_VIEW" for r in rows)
    assert all(r["targetPatientId"] == patient_id for r in rows)


def test_audit_log_outcome_filter_finds_denials(super_user: httpx.Client, receptionist: httpx.Client):
    """거부된 시도가 outcome 필터로 찾아진다."""
    receptionist.post(
        "/api/agent/prescription/recommend",
        headers=csrf_headers(receptionist),
        json={"history_diagnose_id": 1},
    )

    denied = super_user.get("/api/audit/logs", params={"outcome": "DENIED", "size": 50})
    assert denied.status_code == 200

    rows = denied.json()["content"]
    assert rows, "DENIED 필터 결과가 비어 있다"
    assert all(r["outcome"] == "DENIED" for r in rows)


def test_old_super_path_is_gone(super_user: httpx.Client):
    assert super_user.get("/api/super/get_all_users").status_code == 404
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

스택이 아직 이전 이미지를 돌고 있으면 새 API가 없어 실패한다.

```bash
cd /c/Users/kjbdd/Projects/BitComputer
BOOTSTRAP_SUPERUSER_PASSWORD="$(grep '^BOOTSTRAP_SUPERUSER_PASSWORD=' infra/.env | cut -d= -f2-)" \
  python -m pytest tests/e2e -q -k "dept or audit_log or super_path"
```

Expected: 404 또는 필터 미적용으로 실패

- [ ] **Step 3: 스택 재빌드**

```bash
cd infra && docker compose --env-file .env up -d --build spring-boot frontend
```

`spring-boot`이 healthy가 될 때까지 기다린다.

```bash
for i in $(seq 1 40); do
  curl -fsS http://localhost:8080/actuator/health >/dev/null 2>&1 && { echo "ready"; break; }
  sleep 5
done
```

- [ ] **Step 4: 테스트가 통과하는지 확인**

```bash
cd /c/Users/kjbdd/Projects/BitComputer
BOOTSTRAP_SUPERUSER_PASSWORD="$(grep '^BOOTSTRAP_SUPERUSER_PASSWORD=' infra/.env | cut -d= -f2-)" \
  python -m pytest tests/e2e -v
```

Expected: 기존 9개 + 새 6개 = 15개 PASS

- [ ] **Step 5: 멱등성 확인**

```bash
BOOTSTRAP_SUPERUSER_PASSWORD="$(grep '^BOOTSTRAP_SUPERUSER_PASSWORD=' infra/.env | cut -d= -f2-)" \
  python -m pytest tests/e2e -q
```

Expected: 두 번째 실행도 15 passed

- [ ] **Step 6: 전체 검증**

```bash
cd apps/api && ./gradlew test 2>&1 | grep -E "tests completed|BUILD"
cd ../web && ./node_modules/.bin/vitest run 2>&1 | tail -3
```

Expected: Java는 사전 존재 3건만 실패, 프론트 전체 통과

- [ ] **Step 7: 커밋과 푸시**

```bash
cd /c/Users/kjbdd/Projects/BitComputer
git add tests/e2e/test_core_flow.py
git commit -m "test(e2e): 부서 관리와 감사 로그 필터 시나리오 추가" -m "부서 생성·중복 거부·권한 거부, 감사 로그의 action/targetPatientId/outcome
필터, 구 /api/super 경로 제거를 검증한다. 재실행 가능하도록 부서 생성은
201 과 409 를 모두 허용한다."
git push -u origin feat/admin-console
```

---

## 완료 조건 확인

spec 9장의 항목을 순서대로 확인한다.

- [ ] **1. `/admin` 진입 시 감사 화면, 비관리자 차단**

브라우저에서 `http://localhost:3000/admin` → `/admin/audit`로 이동하는지, `DOCTOR` 계정으로는 "관리자만 접근할 수 있습니다"가 뜨는지 확인한다.

- [ ] **2·3. 감사 로그 필터와 DENIED 구분**

```bash
BOOTSTRAP_SUPERUSER_PASSWORD="$(grep '^BOOTSTRAP_SUPERUSER_PASSWORD=' infra/.env | cut -d= -f2-)" \
  python -m pytest tests/e2e -q -k "audit_log"
```

화면에서 결과 필터를 `DENIED`로 두고 행 배경색이 다른지 눈으로 확인한다.

- [ ] **4. 부서 select**

`/admin/users`의 직원 추가 폼에서 부서가 드롭다운인지, 자유 입력이 불가능한지 확인한다.

- [ ] **5. 구 경로 제거**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/super/get_all_users
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/super
```

Expected: 각각 401(인증 없음) 또는 404, 그리고 404

- [ ] **6. DOCTOR 의 /api/admin 접근 차단**

```bash
python -m pytest tests/e2e -q -k "doctor_cannot_create_dept"
```

- [ ] **7. CI green**

```bash
gh pr create --base main --head feat/admin-console --title "feat: 관리자 콘솔 1단계 — 감사 로그 조회와 부서 관리" --body "Docs/superpowers/specs/2026-08-27-admin-console-design.md 의 1단계."
gh run watch
```
