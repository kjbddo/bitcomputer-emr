package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.Repository.PatientRepository;
import com.example.bitcomputer.entity.Patient;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDate;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({TestRedisConfig.class, TestRabbitConfig.class})
class AuditLogTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private JwtTokenProvider jwtTokenProvider;
    @Autowired private AccessAuditLogRepository auditRepository;
    @Autowired private PatientRepository patientRepository;

    private jakarta.servlet.http.Cookie cookieFor(Role role, String username) {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken(username, role));
    }

    @BeforeEach
    void clear() {
        auditRepository.deleteAll();
    }

    @Test
    void patientLookupIsRecorded() throws Exception {
        Patient patient = new Patient();
        patient.setName("환자");
        patient.setPhoneNumber("010-0000-0000");
        patient.setIdentityNumber("audit-log-" + System.nanoTime());
        patient.setVisitNumber("V1");
        patient.setBirth(LocalDate.of(1990, 1, 1));
        patient.setGender("M");
        Patient saved = patientRepository.save(patient);

        mockMvc.perform(get("/api/patients/" + saved.getId()).cookie(cookieFor(Role.DOCTOR, "dr.kim")));

        var logs = auditRepository.findAll();
        assertEquals(1, logs.size());
        assertEquals("dr.kim", logs.get(0).getActorUsername());
        assertEquals("DOCTOR", logs.get(0).getActorRole());
        assertEquals("GRANTED", logs.get(0).getOutcome());
        assertNotNull(logs.get(0).getRequestIp());
        // 인터셉터가 경로 변수에서 대상 환자를 뽑아내는지까지 고정한다.
        // 이 단언이 없으면 경로 변수 이름이 바뀌었을 때 targetPatientId 가 조용히
        // null 로 떨어져도 이 층에서는 아무도 알아채지 못한다(E2E 만이 유일한 방어였다).
        assertEquals(saved.getId(), logs.get(0).getTargetPatientId());
    }

    // I1 회귀: AuditInterceptor 가 preHandle 에서 무조건 GRANTED 를 기록하면, 존재하지
    // 않는 환자를 조회해 404 로 끝난 요청도 GRANTED 로 남는다. afterCompletion 에서
    // 응답 상태를 보고 기록하도록 고친 뒤에는 이런 경우도 DENIED 로 남아야 한다.
    @Test
    void notFoundPatientLookupIsRecordedAsDenied() throws Exception {
        mockMvc.perform(get("/api/patients/999999").cookie(cookieFor(Role.DOCTOR, "dr.kim")))
               .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isNotFound());

        var logs = auditRepository.findAll();
        assertEquals(1, logs.size());
        assertEquals("DENIED", logs.get(0).getOutcome());
    }

    @Test
    @org.springframework.test.annotation.DirtiesContext(
            methodMode = org.springframework.test.annotation.DirtiesContext.MethodMode.AFTER_METHOD)
    void deniedAgentCallIsRecorded() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.RECEPTIONIST, "front.lee"))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"));

        var denied = auditRepository.findAll().stream()
                .filter(l -> "DENIED".equals(l.getOutcome()))
                .toList();
        assertEquals(1, denied.size());
        assertEquals("front.lee", denied.get(0).getActorUsername());
        assertEquals("RECEPTIONIST", denied.get(0).getActorRole());
    }

    // I2 회귀: CSRF 거부(MissingCsrfTokenException 은 AccessDeniedException 의 하위 타입)가
    // RBAC 권한 거부와 같은 ACCESS_DENIED/anonymous 로 뭉개지면 안 된다. action 이
    // 분리돼 있어야 하고, jwtAuthenticationFilter 가 CsrfFilter 보다 앞이므로 쿠키에
    // 유효한 JWT 가 있었다면 actor 도 anonymous 가 아니라 실제 사용자여야 한다.
    @Test
    @org.springframework.test.annotation.DirtiesContext(
            methodMode = org.springframework.test.annotation.DirtiesContext.MethodMode.AFTER_METHOD)
    void csrfRejectionIsRecordedDistinctlyFromRbacDenial() throws Exception {
        mockMvc.perform(post("/api/patients/get_patient_id")
                       .cookie(cookieFor(Role.DOCTOR, "dr.kim"))
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isForbidden());

        var logs = auditRepository.findAll();
        assertEquals(1, logs.size());
        assertEquals("CSRF_REJECTED", logs.get(0).getAction());
        assertEquals("DENIED", logs.get(0).getOutcome());
        assertEquals("dr.kim", logs.get(0).getActorUsername(),
                "jwtAuthenticationFilter 가 CsrfFilter 보다 앞이므로 actor 를 알 수 있어야 한다");
        assertEquals("DOCTOR", logs.get(0).getActorRole());
    }

    @Test
    void auditLogIsReadableBySuperUserOnly() throws Exception {
        mockMvc.perform(get("/api/audit/logs").cookie(cookieFor(Role.SUPER_USER, "admin")))
               .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isOk());

        mockMvc.perform(get("/api/audit/logs").cookie(cookieFor(Role.DOCTOR, "dr.kim")))
               .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isForbidden());
    }

    @Test
    void unannotatedEndpointIsNotRecorded() throws Exception {
        mockMvc.perform(get("/api/diseases?page=0&size=5").cookie(cookieFor(Role.NURSE, "nurse.park")));
        assertTrue(auditRepository.findAll().isEmpty());
    }
}
