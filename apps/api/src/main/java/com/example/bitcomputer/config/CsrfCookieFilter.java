package com.example.bitcomputer.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * {@code CookieCsrfTokenRepository} 는 Spring Security 5.8 이후 CsrfToken 을
 * 지연 로딩한다 — 요청 어딘가에서 토큰 값을 실제로 "읽어야" 그 시점에 쿠키가
 * 구워진다(BREACH 방지 목적). 뷰에 토큰을 렌더링하는 서버사이드 템플릿과 달리
 * 이 애플리케이션은 순수 REST API 라 아무도 토큰을 읽지 않고, 그 결과 SPA 가
 * 읽어야 할 XSRF-TOKEN 쿠키가 영영 내려가지 않는다.
 *
 * 매 요청마다 CsrfToken 이 세팅돼 있으면 강제로 접근해 쿠키 저장을 트리거한다.
 */
@Component
public class CsrfCookieFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                     HttpServletResponse response,
                                     FilterChain filterChain) throws ServletException, IOException {
        CsrfToken csrfToken = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
        if (csrfToken != null) {
            csrfToken.getToken();
        }
        filterChain.doFilter(request, response);
    }
}
