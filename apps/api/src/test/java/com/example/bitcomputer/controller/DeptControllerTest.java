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
        // 이 테스트 클래스는 @DirtiesContext 로 매 테스트 메서드마다 컨텍스트가 재생성되지만,
        // H2 는 컨텍스트가 아니라 스키마 단위로 붙어 있어 같은 실행(run) 안에서 재사용될 수
        // 있다. "내과" 를 고정값으로 쓰면 같은 DB 상태에서 두 번째 실행 시 409 로 깨진다.
        // 실행마다 달라지는 이름을 써서 항상 신규 생성이 되도록 한다.
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
}
