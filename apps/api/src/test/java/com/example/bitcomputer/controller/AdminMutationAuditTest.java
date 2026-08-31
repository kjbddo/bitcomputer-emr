package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.Repository.EmployeeRepository;
import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.config.TestRabbitConfig;
import com.example.bitcomputer.config.TestRedisConfig;
import com.example.bitcomputer.entity.AccessAuditLog;
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

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * I1: AdminController 의 관리자 뮤테이션(직원 생성, 역할 변경)이 @Audited 로
 * 실제 감사 로그를 남기는지 확인한다. 부서 생성·개명은 DeptControllerTest 에
 * 함께 있다(같은 컨트롤러 계열의 기존 테스트 파일에 자연스럽게 딸린다).
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({TestRedisConfig.class, TestRabbitConfig.class})
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class AdminMutationAuditTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private JwtTokenProvider jwtTokenProvider;
    @Autowired private EmployeeRepository employeeRepository;
    @Autowired private AccessAuditLogRepository auditRepository;
    @Autowired private PasswordEncoder passwordEncoder;

    private jakarta.servlet.http.Cookie cookieFor(String username) {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken(username, Role.SUPER_USER));
    }

    private Employee seedEmployee(String username, Role role) {
        Employee employee = new Employee();
        employee.setName(username);
        employee.setUsername(username);
        employee.setPassword(passwordEncoder.encode("irrelevant-pw"));
        employee.setDeptId(1);
        employee.setRole(role);
        return employeeRepository.save(employee);
    }

    @Test
    void creatingEmployeeIsAudited() throws Exception {
        seedEmployee("admin", Role.SUPER_USER);
        String username = "new.doc." + System.nanoTime();

        mockMvc.perform(post("/api/admin/users")
                       .cookie(cookieFor("admin")).with(csrf())
                       .contentType("application/json")
                       .content("{\"name\":\"새직원\",\"username\":\"" + username
                               + "\",\"password\":\"pw12345\",\"deptId\":1,\"role\":\"DOCTOR\"}"))
               .andExpect(status().isCreated());

        List<AccessAuditLog> logs = auditRepository.findAll().stream()
                .filter(l -> "USER_CREATE".equals(l.getAction()))
                .toList();
        assertEquals(1, logs.size());
        assertEquals("GRANTED", logs.get(0).getOutcome());
        assertEquals("admin", logs.get(0).getActorUsername());
        // 이 경로 변수는 대상 직원 ID 이지 환자 ID 가 아니다 - null 로 남아야 한다.
        assertNull(logs.get(0).getTargetPatientId());
    }

    @Test
    void roleChangeIsAudited() throws Exception {
        seedEmployee("admin", Role.SUPER_USER);
        Employee target = seedEmployee("target." + System.nanoTime(), Role.DOCTOR);

        // SUPER_USER 승격 - 시스템에서 가장 강력한 권한 행위다.
        mockMvc.perform(put("/api/admin/users/" + target.getId() + "/role")
                       .cookie(cookieFor("admin")).with(csrf())
                       .contentType("application/json")
                       .content("{\"role\":\"SUPER_USER\"}"))
               .andExpect(status().isOk());

        List<AccessAuditLog> logs = auditRepository.findAll().stream()
                .filter(l -> "ROLE_CHANGE".equals(l.getAction()))
                .toList();
        assertEquals(1, logs.size());
        assertEquals("GRANTED", logs.get(0).getOutcome());
        assertEquals("admin", logs.get(0).getActorUsername());
        assertNull(logs.get(0).getTargetPatientId());
    }
}
