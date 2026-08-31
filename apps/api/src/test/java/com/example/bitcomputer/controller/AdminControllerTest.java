package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.EmployeeRepository;
import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.config.TestRabbitConfig;
import com.example.bitcomputer.config.TestRedisConfig;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({TestRedisConfig.class, TestRabbitConfig.class})
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AdminControllerTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private JwtTokenProvider jwtTokenProvider;
    @Autowired private EmployeeRepository employeeRepository;
    @Autowired private PasswordEncoder passwordEncoder;

    private jakarta.servlet.http.Cookie cookieFor(String username) {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken(username, Role.SUPER_USER));
    }

    /**
     * AdminController.validateSuperUser 는 SecurityConfig 의 역할 체크와 별개로
     * employeeRepository.findByUsername(...) 으로 요청자를 다시 조회한다 - 쿠키의
     * JWT 만으로는 부족하고, DB 에 실제로 그 username 의 SUPER_USER 직원 행이
     * 있어야 한다.
     */
    private Employee seedEmployee(String username, Role role) {
        Employee employee = new Employee();
        employee.setName(username);
        employee.setUsername(username);
        employee.setPassword(passwordEncoder.encode("irrelevant-pw"));
        employee.setDeptId(1);
        employee.setRole(role);
        return employeeRepository.save(employee);
    }

    // ── C1: 비밀번호 해시가 응답에 새지 않는다 ──────────────────────

    @Test
    void userListResponseNeverContainsPasswordField() throws Exception {
        seedEmployee("admin", Role.SUPER_USER);

        mockMvc.perform(get("/api/admin/users").cookie(cookieFor("admin")))
               .andExpect(status().isOk())
               .andExpect(jsonPath("$[*].password").doesNotExist());
    }
}
