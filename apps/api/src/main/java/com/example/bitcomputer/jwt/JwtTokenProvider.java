package com.example.bitcomputer.jwt;

import com.example.bitcomputer.entity.Role;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.util.Date;

@Component
public class JwtTokenProvider {

    /** HS512 서명에 필요한 최소 키 길이(바이트). */
    private static final int MIN_SECRET_BYTES = 64;

    private static final long ACCESS_TOKEN_VALIDITY_SECONDS = 28800L;   // 8시간
    private static final long REFRESH_TOKEN_VALIDITY_SECONDS = 604800L; // 7일

    private static final String CLAIM_ROLE = "role";

    @Value("${jwt.secret}")
    private String secretKey;

    private Key SECRET_KEY;

    @PostConstruct
    public void init() {
        if (secretKey == null || secretKey.getBytes(StandardCharsets.UTF_8).length < MIN_SECRET_BYTES) {
            throw new IllegalStateException(
                    "jwt.secret 이 너무 짧습니다. HS512 서명에는 최소 " + MIN_SECRET_BYTES
                            + "바이트가 필요합니다. `openssl rand -base64 64` 로 생성하세요.");
        }
        this.SECRET_KEY = Keys.hmacShaKeyFor(secretKey.getBytes(StandardCharsets.UTF_8));
    }

    public long getAccessTokenValiditySeconds() {
        return ACCESS_TOKEN_VALIDITY_SECONDS;
    }

    public long getRefreshTokenValiditySeconds() {
        return REFRESH_TOKEN_VALIDITY_SECONDS;
    }

    public String generateAccessToken(String username, Role role) {
        return build(username, role, ACCESS_TOKEN_VALIDITY_SECONDS);
    }

    public String generateRefreshToken(String username) {
        return build(username, null, REFRESH_TOKEN_VALIDITY_SECONDS);
    }

    private String build(String username, Role role, long validitySeconds) {
        requireInitialized();
        long now = System.currentTimeMillis();
        var builder = Jwts.builder()
                .setSubject(username)
                .setIssuedAt(new Date(now))
                .setExpiration(new Date(now + validitySeconds * 1000L));
        if (role != null) {
            builder.claim(CLAIM_ROLE, role.name());
        }
        return builder.signWith(SECRET_KEY, SignatureAlgorithm.HS512).compact();
    }

    public boolean validateToken(String token) {
        if (SECRET_KEY == null || token == null || token.isEmpty()) {
            return false;
        }
        try {
            parse(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public String extractUsername(String token) {
        return parse(token).getSubject();
    }

    public Role extractRole(String token) {
        String raw = parse(token).get(CLAIM_ROLE, String.class);
        if (raw == null) {
            return Role.DEFAULT;
        }
        try {
            return Role.valueOf(raw);
        } catch (IllegalArgumentException e) {
            return Role.DEFAULT;
        }
    }

    public long getExpiration(String token) {
        return parse(token).getExpiration().getTime();
    }

    private Claims parse(String token) {
        requireInitialized();
        return Jwts.parserBuilder()
                .setSigningKey(SECRET_KEY)
                .build()
                .parseClaimsJws(token)
                .getBody();
    }

    private void requireInitialized() {
        if (SECRET_KEY == null) {
            throw new IllegalStateException("SECRET_KEY is not initialized. Check jwt.secret configuration.");
        }
    }
}
