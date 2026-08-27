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
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import({TestRedisConfig.class, TestRabbitConfig.class})
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

    // 실제 브라우저 SPA 는 SecurityMockMvcRequestPostProcessors.csrf() 를 쓰지 않는다.
    // GET 으로 XSRF-TOKEN 쿠키를 받아, 그 쿠키의 "원문" 값을 그대로 X-XSRF-TOKEN
    // 헤더에 실어 POST 를 보낸다 — axios 의 xsrfCookieName/xsrfHeaderName 옵션,
    // 그리고 apps/web/src/services/http/client.ts 가 정확히 이렇게 동작한다.
    // csrf() 헬퍼는 리플렉션으로 헤더 값을 자동으로 만들어 마스킹 여부와 무관하게
    // 통과시켜 버리므로 이 결함을 가려버린다 — 그래서 이 테스트는 csrf() 를 쓰지
    // 않고 실제 더블서브밋 왕복을 그대로 재현한다.
    //
    // SecurityConfig 가 CookieCsrfTokenRepository.withHttpOnlyFalse() 와 함께
    // csrfTokenRequestHandler 를 지정하지 않으면 Spring Security 6 기본값인
    // XorCsrfTokenRequestAttributeHandler 가 적용되는데, 이 핸들러는 헤더 값이
    // BREACH 방지용으로 XOR 마스킹돼 있다고 가정하고 디코딩을 시도한다. 하지만
    // 쿠키에는 마스킹되지 않은 원문 토큰이 그대로 담기므로, 이를 그대로 헤더에
    // 실어 보내면 디코딩 결과가 실제 토큰과 달라져 403 이 발생한다. 이 테스트는
    // 그 회귀를 잡기 위한 것이다.
    @Test
    void doubleSubmitWithRawCookieValueInHeaderPassesCsrfCheck() throws Exception {
        MvcResult getResult = mockMvc.perform(get("/actuator/health"))
                .andExpect(status().is(org.hamcrest.Matchers.not(403)))
                .andReturn();

        jakarta.servlet.http.Cookie xsrfCookie = getResult.getResponse().getCookie("XSRF-TOKEN");
        org.junit.jupiter.api.Assertions.assertNotNull(xsrfCookie, "XSRF-TOKEN 쿠키가 응답에 없다");
        String rawToken = xsrfCookie.getValue();

        mockMvc.perform(post("/api/patients")
                       .cookie(doctorCookie(), xsrfCookie)
                       .header("X-XSRF-TOKEN", rawToken)
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    // 회귀 방지: csrfTokenRequestHandler 만으로는 잡히지 않는 별개의 결함이다.
    //
    // HttpSecurity.csrf(...) 는 항상 CsrfAuthenticationStrategy 를
    // SessionManagementConfigurer 에 등록해, SessionManagementFilter 가 "이번 요청에서
    // 처음 인증됨"이라 판단할 때마다 XSRF-TOKEN 쿠키를 지우고(saveToken(null, ...))
    // 다시 굽게 한다 — 로그인 시점에 CSRF 토큰을 회전시켜 고정 공격을 막으려는
    // 의도다. 그런데 "처음 인증됨"의 판정은 SessionManagementFilter 가
    // securityContextRepository.containsContext(request) 로 하는데, 이 앱처럼
    // SessionCreationPolicy.STATELESS(=NullSecurityContextRepository) 를 쓰고
    // JwtAuthenticationFilter 가 매 요청마다 쿠키의 JWT 로 SecurityContext 를 새로
    // 채우는 구조에서는 이 판정이 인증된 "모든" 요청에서 항상 true 로 나온다.
    // 그 결과 인증된 요청마다(GET 포함) XSRF-TOKEN 쿠키가 삭제된 채로 응답이 나가,
    // SPA 가 들고 있던 쿠키가 다음 요청 때는 이미 사라져 있다 — 두 번째 인증된
    // 요청부터 CSRF 403 이 난다. SecurityConfig 의
    // .sessionAuthenticationStrategy(new NullAuthenticatedSessionStrategy()) 가 이를 끈다.
    //
    // 이 결함은 한 번의 왕복(GET→POST)만으로는 드러나지 않는다 — 첫 인증 요청까지는
    // 쿠키가 아직 없어 삭제 로직 자체가 스킵되기 때문이다(doubleSubmitWithRawCookieValueInHeaderPassesCsrfCheck()
    // 참고). 그래서 인증된 요청을 "연속으로 두 번" 보내, 두 번째 응답에서도 여전히
    // 쿠키가 살아있는지를 확인해야 한다.
    @Test
    void secondConsecutiveAuthenticatedRequestKeepsCsrfCookieAlive() throws Exception {
        MvcResult first = mockMvc.perform(get("/actuator/health").cookie(doctorCookie()))
                .andExpect(status().is(org.hamcrest.Matchers.not(403)))
                .andReturn();

        jakarta.servlet.http.Cookie firstXsrf = first.getResponse().getCookie("XSRF-TOKEN");
        org.junit.jupiter.api.Assertions.assertNotNull(firstXsrf, "첫 인증 요청에서 XSRF-TOKEN 쿠키가 없다");

        MvcResult second = mockMvc.perform(get("/actuator/health").cookie(doctorCookie(), firstXsrf))
                .andExpect(status().is(org.hamcrest.Matchers.not(403)))
                .andReturn();

        String setCookieHeader = second.getResponse().getHeader("Set-Cookie");
        boolean deletedXsrfCookie = setCookieHeader != null && setCookieHeader.startsWith("XSRF-TOKEN=;");
        org.junit.jupiter.api.Assertions.assertFalse(deletedXsrfCookie,
                "두 번째 인증 요청에서 XSRF-TOKEN 쿠키가 삭제됐다(SessionManagementFilter 가 매 요청을 "
                        + "'새 인증'으로 오판): " + setCookieHeader);
    }
}
