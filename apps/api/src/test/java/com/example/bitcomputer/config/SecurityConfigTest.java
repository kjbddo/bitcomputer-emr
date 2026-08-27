package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.EmployeeRepository;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@org.springframework.context.annotation.Import({TestRedisConfig.class, TestRabbitConfig.class})
class SecurityConfigTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    @Autowired
    private EmployeeRepository employeeRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    // AdminController 는 SecurityConfig 의 hasRole("SUPER_USER") 와는 별개로,
    // 요청자를 employeeRepository 에서 실제로 조회해 SUPER_USER 인지 다시 확인한다
    // (validateSuperUser/extractEmployee). 그 belt-and-braces 검증을 통과하려면
    // cookieFor 가 심는 "tester" 사용자가 실제로 DB 에 SUPER_USER 로 존재해야 한다.
    private void ensureTesterIsSeededAsSuperUser() {
        if (employeeRepository.findByUsername("tester") != null) {
            return;
        }
        Employee tester = new Employee();
        tester.setName("tester");
        tester.setUsername("tester");
        tester.setPassword(passwordEncoder.encode("unused"));
        tester.setDeptId(1);
        tester.setRole(Role.SUPER_USER);
        employeeRepository.save(tester);
    }

    private jakarta.servlet.http.Cookie cookieFor(Role role) {
        String token = jwtTokenProvider.generateAccessToken("tester", role);
        return new jakarta.servlet.http.Cookie(CookieFactory.ACCESS_TOKEN_COOKIE, token);
    }

    @Test
    void patientApiRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/patients/1"))
               .andExpect(status().isUnauthorized());
    }

    // 로그인 실패는 (버그 수정 이후) 컨트롤러가 정당하게 401 을 응답하므로,
    // "401 이 아니어야 한다"는 더 이상 "필터 체인에 막히지 않았다"의 증거가
    // 못 된다 — 둘 다 401 이 나올 수 있다. 대신 필터 단에서 막힌 경우
    // (HttpStatusEntryPoint, 본문 없음/기본 에러 페이지)와 컨트롤러까지 도달해
    // 인증 실패 메시지를 응답한 경우를 본문으로 구분한다.
    @Test
    void loginEndpointIsPublic() throws Exception {
        mockMvc.perform(post("/api/user/login")
                       .contentType("application/json")
                       .content("{\"username\":\"none\",\"password\":\"none\"}"))
               .andExpect(status().isUnauthorized())
               .andExpect(content().string("Invalid username or password"));
    }

    @Test
    void actuatorHealthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
               .andExpect(status().isOk());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void receptionistCannotCallAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.RECEPTIONIST))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void nurseCannotCallAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.NURSE))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void doctorReachesAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.DOCTOR))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void defaultRoleIsDeniedEverywhere() throws Exception {
        mockMvc.perform(get("/api/patients/1")
                       .cookie(cookieFor(Role.DEFAULT)))
               .andExpect(status().isForbidden());
    }

    // I3 회귀: /api/history-diagnoses/**, /api/history-diseases/** 매처는 실제로 존재하지
    // 않는 경로였다(컨트롤러는 전부 "/api/histories" 아래 매핑돼 있다). 그 결과 GET 은
    // 아무 제한 없이 anyRequest().hasAnyRole(RECEPTIONIST, NURSE, DOCTOR, SUPER_USER) 로
    // 떨어져, 원무(RECEPTIONIST)가 처방·상병·진료이력·AI 검증 결과까지 읽을 수 있었다.
    @Test
    void receptionistCannotReadPrescriptions() throws Exception {
        mockMvc.perform(get("/api/histories/1/get_diagnoses")
                       .cookie(cookieFor(Role.RECEPTIONIST)))
               .andExpect(status().isForbidden());
    }

    @Test
    void receptionistCannotReadDiseases() throws Exception {
        mockMvc.perform(get("/api/histories/1/get_diseases")
                       .cookie(cookieFor(Role.RECEPTIONIST)))
               .andExpect(status().isForbidden());
    }

    @Test
    void receptionistCannotSearchHistory() throws Exception {
        mockMvc.perform(get("/api/histories/search_history/1")
                       .param("patientId", "1")
                       .cookie(cookieFor(Role.RECEPTIONIST)))
               .andExpect(status().isForbidden());
    }

    @Test
    void receptionistCannotReadValidationResults() throws Exception {
        mockMvc.perform(get("/api/histories/1/validation_results")
                       .param("employeeId", "1")
                       .cookie(cookieFor(Role.RECEPTIONIST)))
               .andExpect(status().isForbidden());
    }

    // validation_results 는 AI 기능이라 NURSE 도 접근할 수 없어야 한다(5.3 "AI 엔드포인트는
    // DOCTOR 전용" — NURSE 는 "처방 조회(읽기)" 권한만 있다).
    @Test
    void nurseCannotReadValidationResults() throws Exception {
        mockMvc.perform(get("/api/histories/1/validation_results")
                       .param("employeeId", "1")
                       .cookie(cookieFor(Role.NURSE)))
               .andExpect(status().isForbidden());
    }

    @Test
    void nurseCanReadPrescriptions() throws Exception {
        mockMvc.perform(get("/api/histories/1/get_diagnoses")
                       .param("employeeId", "1")
                       .cookie(cookieFor(Role.NURSE)))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

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
        ensureTesterIsSeededAsSuperUser();
        mockMvc.perform(get("/api/admin/users")
                       .cookie(cookieFor(Role.SUPER_USER)))
               .andExpect(status().isOk());
    }
}
