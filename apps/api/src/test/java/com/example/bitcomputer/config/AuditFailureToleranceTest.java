package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.Repository.PatientRepository;
import com.example.bitcomputer.entity.Patient;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDate;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 감사 로그 저장이 실패해도(제약 위반, 감사 DB 다운 등) 임상 요청 자체는 막히면
 * 안 된다는 fail-open 정책을 검증한다. (AuditInterceptor / RestAccessDeniedHandler 참고)
 */
@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestRedisConfig.class)
class AuditFailureToleranceTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    @Autowired
    private PatientRepository patientRepository;

    @MockitoBean
    private AccessAuditLogRepository accessAuditLogRepository;

    private jakarta.servlet.http.Cookie cookieFor(Role role, String username) {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken(username, role));
    }

    @Test
    void grantedPatientLookupStillSucceedsWhenAuditWriteThrows() throws Exception {
        when(accessAuditLogRepository.save(any())).thenThrow(new RuntimeException("감사 DB 장애 시뮬레이션"));

        Patient patient = new Patient();
        patient.setName("환자");
        patient.setPhoneNumber("010-0000-0000");
        patient.setIdentityNumber("audit-fail-open-" + System.nanoTime());
        patient.setVisitNumber("V1");
        patient.setBirth(LocalDate.of(1990, 1, 1));
        patient.setGender("M");
        Patient saved = patientRepository.save(patient);

        // AuditInterceptor#preHandle 이 auditService.record(...) 예외를 삼키지 않으면
        // 컨트롤러 호출 자체가 무산돼 의사가 정상 환자 조회조차 하지 못하게 된다.
        mockMvc.perform(get("/api/patients/" + saved.getId()).cookie(cookieFor(Role.DOCTOR, "dr.kim")))
               .andExpect(status().isOk());
    }

    // .with(csrf()) 는 실제 CsrfFilter 싱글턴의 tokenRepository 를 세션 기반으로 영구
    // 교체한다(CsrfTest 의 관련 주석 참고). 이 클래스 컨텍스트를 다른 테스트가 공유할
    // 가능성을 차단하기 위해 방어적으로 격리한다.
    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void deniedRequestStillReturns403WhenAuditWriteThrows() throws Exception {
        when(accessAuditLogRepository.save(any())).thenThrow(new RuntimeException("감사 DB 장애 시뮬레이션"));

        // RestAccessDeniedHandler#handle 이 auditService.record(...) 예외를 삼키지 않으면
        // 예외가 핸들러 밖으로 새어나가 의도한 403 대신 500 으로 응답하게 된다.
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.RECEPTIONIST, "front.lee"))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }
}
