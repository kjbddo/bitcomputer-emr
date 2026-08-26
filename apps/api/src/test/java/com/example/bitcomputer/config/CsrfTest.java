package com.example.bitcomputer.config;

import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestRedisConfig.class)
class CsrfTest {

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
    void postWithoutCsrfTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/api/patients")
                       .cookie(doctorCookie())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfTokenPassesCsrfCheck() throws Exception {
        mockMvc.perform(post("/api/patients")
                       .cookie(doctorCookie())
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void getRequestsSkipCsrfCheck() throws Exception {
        mockMvc.perform(get("/api/patients/1").cookie(doctorCookie()))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void loginIsExemptFromCsrf() throws Exception {
        mockMvc.perform(post("/api/user/login")
                       .contentType("application/json")
                       .content("{\"username\":\"none\",\"password\":\"none\"}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void getResponseIssuesReadableXsrfCookie() throws Exception {
        // SPA 는 document.cookie 로 XSRF-TOKEN 값을 읽어 X-XSRF-TOKEN 헤더에 실어 보낸다.
        // 이 쿠키가 HttpOnly 이면 axios 가 절대 값을 읽을 수 없으므로, 여기서
        // "존재 + HttpOnly 아님" 을 함께 고정해 둔다.
        mockMvc.perform(get("/api/patients/1").cookie(doctorCookie()))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)))
               .andExpect(cookie().exists("XSRF-TOKEN"))
               .andExpect(cookie().httpOnly("XSRF-TOKEN", false));
    }

    @Test
    void logoutWithoutCsrfTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/api/user/logout")
                       .cookie(doctorCookie()))
               .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithCsrfTokenPassesCsrfCheck() throws Exception {
        mockMvc.perform(post("/api/user/logout")
                       .cookie(doctorCookie())
                       .with(csrf()))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }
}
