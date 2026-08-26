package com.example.bitcomputer.controller;

import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.config.TestRedisConfig;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * GlobalExceptionHandler 가 ResponseStatusException 을 그 자체 상태 코드로 응답하는지
 * 확인한다. 이 핸들러가 없으면 handleRuntimeException 이 ResponseStatusException 을
 * 먼저 잡아 무조건 500 으로 응답해 버린다(GlobalExceptionHandler 참고).
 */
@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestRedisConfig.class)
class PatientNotFoundIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    private jakarta.servlet.http.Cookie doctorCookie() {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken("dr.kim", Role.DOCTOR));
    }

    @Test
    void getPatientWithNonexistentIdReturns404NotInternalServerError() throws Exception {
        // 이 테스트 컨텍스트 전용 H2 DB 는 비어 있는 상태로 시작하므로, id 는
        // 존재하지 않는 것이 보장된다(application-test.properties 의
        // ${random.uuid} 격리 참고).
        mockMvc.perform(get("/api/patients/999999").cookie(doctorCookie()))
               .andExpect(status().isNotFound());
    }
}
