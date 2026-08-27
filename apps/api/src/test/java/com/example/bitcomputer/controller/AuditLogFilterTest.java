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
