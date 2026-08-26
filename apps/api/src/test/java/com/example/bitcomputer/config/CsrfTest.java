package com.example.bitcomputer.config;

import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;
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

    // SecurityMockMvcRequestPostProcessors.csrf() 는 리플렉션으로 실제 CsrfFilter 싱글턴
    // 빈의 tokenRepository 필드를 세션 기반 HttpSessionCsrfTokenRepository 로 영구
    // 교체해 버린다(원복 로직이 없다). 같은 설정을 쓰는 다른 테스트 클래스는 캐시된
    // 같은 Spring 컨텍스트/같은 CsrfFilter 인스턴스를 공유하므로, 이 오염이 실행 순서에
    // 따라 getResponseIssuesReadableXsrfCookie() 등 다른 테스트로 새어나가
    // CookieCsrfTokenRepository 가 써야 할 XSRF-TOKEN 쿠키가 사라지는 간헐적 실패를
    // 일으켰다. @DirtiesContext(AFTER_METHOD) 로 이 메서드가 끝나면 오염된 컨텍스트를
    // 버려서, 이후 테스트는 항상 깨끗한 CsrfFilter 로 시작하게 한다.
    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
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
        //
        // CsrfCookieFilter 는 인증/권한/DB 상태와 무관하게 CsrfToken 이 세팅된 모든
        // 요청에서 쿠키를 굽는다. 예전에는 /api/patients/1 로 찔러봤는데, 그 환자가
        // 실제로 존재하는지가 테스트 실행 순서에 따라 달라져(H2 인메모리 DB) 없는
        // 경우 서비스가 404 로 예외를 던졌고, 그게 500 으로 뭉개지며 XSRF-TOKEN
        // 쿠키 없이 응답해 테스트가 간헐적으로 실패했다. /actuator/health 는 인증도
        // DB 조회도 필요 없는 permitAll 엔드포인트라 이 검증에 데이터 상태가
        // 끼어들 여지가 없다.
        mockMvc.perform(get("/actuator/health"))
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

    // postWithCsrfTokenPassesCsrfCheck() 위 주석 참고 — 같은 이유로 오염 격리가 필요하다.
    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void logoutWithCsrfTokenPassesCsrfCheck() throws Exception {
        mockMvc.perform(post("/api/user/logout")
                       .cookie(doctorCookie())
                       .with(csrf()))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }
}
