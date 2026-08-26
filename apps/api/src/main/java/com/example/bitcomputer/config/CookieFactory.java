package com.example.bitcomputer.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.http.ResponseCookie;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.Locale;

/**
 * 인증 쿠키 생성기.
 *
 * access token 은 HttpOnly 로 내려 JS 가 읽지 못하게 한다. XSS 로 토큰이
 * 탈취되는 경로를 막기 위한 것이며, 프론트는 토큰 값을 알 필요가 없다.
 */
@Component
public class CookieFactory {

    private static final Logger log = LoggerFactory.getLogger(CookieFactory.class);

    /** 로컬/개발용으로 간주해 경고를 건너뛰는 프로필 이름들. */
    private static final java.util.Set<String> LOCAL_LIKE_PROFILES = java.util.Set.of("local", "dev", "development");

    public static final String ACCESS_TOKEN_COOKIE = "access_token";

    private final boolean secure;
    private final String activeProfiles;

    public CookieFactory(@Value("${auth.cookie.secure:false}") boolean secure,
                          @Value("${spring.profiles.active:}") String activeProfiles) {
        this.secure = secure;
        this.activeProfiles = activeProfiles;
    }

    /**
     * secure 쿠키가 꺼져 있는데 로컬/개발 프로필이 아닌 경우(=배포 환경으로 추정) true.
     * 부팅 시 1회 경고 로그를 위한 조건이며, 기동 자체를 막지는 않는다 — 로컬 개발은
     * http 로도 정상 동작해야 하기 때문이다.
     */
    static boolean isInsecureCookieInDeployment(boolean secure, String activeProfiles) {
        if (secure) {
            return false;
        }
        if (activeProfiles == null || activeProfiles.isBlank()) {
            // spring.profiles.active 가 비어 있으면 프로필 정보가 없다는 뜻이라 배포 여부를
            // 단정할 수 없다 — 오탐(false positive)을 피하기 위해 경고하지 않는다.
            return false;
        }
        for (String profile : activeProfiles.split(",")) {
            if (LOCAL_LIKE_PROFILES.contains(profile.trim().toLowerCase(Locale.ROOT))) {
                return false;
            }
        }
        return true;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void warnIfCookieInsecureInDeployment() {
        if (isInsecureCookieInDeployment(secure, activeProfiles)) {
            log.warn("auth.cookie.secure=false 인 채로 배포용 프로필(spring.profiles.active={})로 기동되었습니다. "
                            + "HTTPS 환경이라면 인증 쿠키가 평문으로 전송될 수 있습니다. "
                            + "환경변수 AUTH_COOKIE_SECURE=true 를 설정하세요.",
                    activeProfiles);
        }
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
