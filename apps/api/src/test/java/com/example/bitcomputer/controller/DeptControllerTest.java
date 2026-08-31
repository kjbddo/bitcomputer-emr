package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.Repository.DeptRepository;
import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.config.TestRabbitConfig;
import com.example.bitcomputer.config.TestRedisConfig;
import com.example.bitcomputer.entity.AccessAuditLog;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
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
    @Autowired private AccessAuditLogRepository auditRepository;
    private final ObjectMapper objectMapper = new ObjectMapper();

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
        // 이름을 실행마다 다르게 만드는 것은 방어적 조치다.
        // application-test.properties 가 jdbc:h2:mem:testdb-${random.uuid} 로 컨텍스트마다
        // 독립된 H2 를 쓰고, 이 클래스는 @DirtiesContext(AFTER_EACH_TEST_METHOD) 라
        // 메서드마다 DB 가 새로 만들어진다 — 고정 이름을 써도 충돌하지 않는다.
        // 다만 위 두 조건 중 하나라도 바뀌면 조용히 409 로 깨지므로 유일한 이름을 유지한다.
        String deptName = "내과-" + System.nanoTime();
        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"" + deptName + "\"}"))
               .andExpect(status().isCreated())
               .andExpect(jsonPath("$.dept").value(deptName));
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

    // ── I1: 부서 생성·개명이 감사에 남는다 ──────────────────────────

    @Test
    void creatingDeptIsAudited() throws Exception {
        String deptName = "감사확인과-" + System.nanoTime();

        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"" + deptName + "\"}"))
               .andExpect(status().isCreated());

        List<AccessAuditLog> logs = auditRepository.findAll().stream()
                .filter(l -> "DEPT_CREATE".equals(l.getAction()))
                .toList();
        assertEquals(1, logs.size());
        assertEquals("GRANTED", logs.get(0).getOutcome());
        // 경로 변수가 없는 생성 엔드포인트다 - 애초에 patientId 를 뽑을 경로 변수가 없다.
        assertNull(logs.get(0).getTargetPatientId());
    }

    @Test
    void renamingDeptIsAudited() throws Exception {
        String original = "원래과-" + System.nanoTime();
        String createdBody = mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"" + original + "\"}"))
               .andExpect(status().isCreated())
               .andReturn().getResponse().getContentAsString();
        int id = objectMapper.readTree(createdBody).get("id").asInt();

        mockMvc.perform(put("/api/admin/depts/" + id)
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"바뀐과-" + System.nanoTime() + "\"}"))
               .andExpect(status().isOk());

        List<AccessAuditLog> logs = auditRepository.findAll().stream()
                .filter(l -> "DEPT_RENAME".equals(l.getAction()))
                .toList();
        assertEquals(1, logs.size());
        assertEquals("GRANTED", logs.get(0).getOutcome());
        // "{id}" 경로 변수는 부서 ID 이지 환자 ID 가 아니다 - null 로 남아야 한다(I1).
        assertNull(logs.get(0).getTargetPatientId());
    }

    // ── M9: 잘못된 요청 본문/경로 변수는 500 이 아니라 400 이어야 한다 ──────

    @Test
    void malformedJsonBodyOnCreateReturns400() throws Exception {
        mockMvc.perform(post("/api/admin/depts")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{이건 json 이 아님"))
               .andExpect(status().isBadRequest());
    }

    @Test
    void nonNumericIdOnRenameReturns400() throws Exception {
        mockMvc.perform(put("/api/admin/depts/not-a-number")
                       .cookie(cookieFor(Role.SUPER_USER)).with(csrf())
                       .contentType("application/json")
                       .content("{\"dept\":\"아무과\"}"))
               .andExpect(status().isBadRequest());
    }
}
