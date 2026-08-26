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
}
