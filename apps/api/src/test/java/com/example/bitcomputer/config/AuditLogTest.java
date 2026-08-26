package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestRedisConfig.class)
class AuditLogTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private JwtTokenProvider jwtTokenProvider;
    @Autowired private AccessAuditLogRepository auditRepository;

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
        mockMvc.perform(get("/api/patients/1").cookie(cookieFor(Role.DOCTOR, "dr.kim")));

        var logs = auditRepository.findAll();
        assertEquals(1, logs.size());
        assertEquals("dr.kim", logs.get(0).getActorUsername());
        assertEquals("DOCTOR", logs.get(0).getActorRole());
        assertEquals("GRANTED", logs.get(0).getOutcome());
        assertNotNull(logs.get(0).getRequestIp());
    }

    @Test
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
