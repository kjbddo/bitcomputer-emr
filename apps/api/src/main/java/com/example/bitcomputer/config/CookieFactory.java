package com.example.bitcomputer.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 인증 쿠키 생성기.
 *
 * access token 은 HttpOnly 로 내려 JS 가 읽지 못하게 한다. XSS 로 토큰이
 * 탈취되는 경로를 막기 위한 것이며, 프론트는 토큰 값을 알 필요가 없다.
 */
@Component
public class CookieFactory {

    public static final String ACCESS_TOKEN_COOKIE = "access_token";

    private final boolean secure;

    public CookieFactory(@Value("${auth.cookie.secure:false}") boolean secure) {
        this.secure = secure;
    }

    public ResponseCookie accessTokenCookie(String token, long maxAgeSeconds) {
        return ResponseCookie.from(ACCESS_TOKEN_COOKIE, token)
                .httpOnly(true)
                .secure(secure)
                .sameSite("Lax")
                .path("/")
                .maxAge(Duration.ofSeconds(maxAgeSeconds))
                .build();
    }

    public ResponseCookie expiredAccessTokenCookie() {
        return ResponseCookie.from(ACCESS_TOKEN_COOKIE, "")
                .httpOnly(true)
                .secure(secure)
                .sameSite("Lax")
                .path("/")
                .maxAge(Duration.ZERO)
                .build();
    }
}
