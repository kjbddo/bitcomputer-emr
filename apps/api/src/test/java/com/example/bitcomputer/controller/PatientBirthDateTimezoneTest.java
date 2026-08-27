package com.example.bitcomputer.controller;

import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.config.TestRabbitConfig;
import com.example.bitcomputer.config.TestRedisConfig;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * C1 회귀 테스트: 환자 생년월일이 시간대 변환 때문에 하루 밀리던 결함.
 *
 * application.properties(main) 는 spring.jackson.time-zone=Asia/Seoul 을 강제하는데,
 * 예전 PatientServiceImpl 은 이 값을 ZoneId.systemDefault() 로 다시 변환했다. 두 존이
 * 다르면(JVM 기본 시간대가 Asia/Seoul 이 아니면) "1990-01-01" 이 "1989-12-31" 로
 * 영구히 밀렸다 — GET 으로 조회해도 밀린 값이 그대로 나왔다.
 *
 * 이 테스트는 실제 배포와 동일하게 spring.jackson.time-zone=Asia/Seoul 을 강제한 채
 * (test 프로파일의 application.properties 는 이 값을 비워 main 설정을 가리므로 여기서
 * 명시적으로 되살린다) 생성→조회 왕복이 입력한 날짜를 그대로 보존하는지 검증한다.
 *
 * -Duser.timezone=UTC 로 실행하면 수정 전 코드에서는 실패하고, 수정 후에는
 * (PatientDTO.birth 가 LocalDate 라 애초에 시간대 변환이 없으므로) 어떤 JVM 기본
 * 시간대에서도 통과한다.
 */
@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({TestRedisConfig.class, TestRabbitConfig.class})
@TestPropertySource(properties = "spring.jackson.time-zone=Asia/Seoul")
class PatientBirthDateTimezoneTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    @Autowired
    private ObjectMapper objectMapper;

    private jakarta.servlet.http.Cookie receptionistCookie() {
        return new jakarta.servlet.http.Cookie(
                CookieFactory.ACCESS_TOKEN_COOKIE,
                jwtTokenProvider.generateAccessToken("front.desk", Role.RECEPTIONIST));
    }

    @Test
    void createdPatientBirthDateSurvivesRoundTripRegardlessOfJvmDefaultTimezone() throws Exception {
        String requestBody = """
                {
                  "name": "홍길동",
                  "phoneNumber": "010-0000-0000",
                  "identityNumber": "900101-1234567",
                  "visitNumber": "V-TZ-0001",
                  "gender": "M",
                  "birth": "1990-01-01"
                }
                """;

        MvcResult createResult = mockMvc.perform(post("/api/patients/get_patient_id")
                        .cookie(receptionistCookie())
                        .with(csrf())
                        .contentType("application/json")
                        .content(requestBody))
                .andExpect(status().isCreated())
                .andReturn();

        JsonNode created = objectMapper.readTree(createResult.getResponse().getContentAsString());
        int patientId = created.get("patientId").asInt();

        MvcResult getResult = mockMvc.perform(get("/api/patients/" + patientId)
                        .cookie(receptionistCookie()))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode fetched = objectMapper.readTree(getResult.getResponse().getContentAsString());
        assertEquals("1990-01-01", fetched.get("birth").asText(),
                "생년월일이 시간대 변환으로 밀렸다 — 입력한 날짜와 조회된 날짜가 달라야 할 이유가 없다.");
    }
}
