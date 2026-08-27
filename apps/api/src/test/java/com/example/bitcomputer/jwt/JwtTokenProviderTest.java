package com.example.bitcomputer.jwt;

import com.example.bitcomputer.entity.Role;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.*;

class JwtTokenProviderTest {

    private static final String VALID_SECRET =
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    private JwtTokenProvider provider;

    @BeforeEach
    void setUp() {
        provider = new JwtTokenProvider();
        ReflectionTestUtils.setField(provider, "secretKey", VALID_SECRET);
        provider.init();
    }

    @Test
    void generatedTokenCarriesUsername() {
        String token = provider.generateAccessToken("dr.kim", Role.DOCTOR);
        assertEquals("dr.kim", provider.extractUsername(token));
    }

    @Test
    void generatedTokenCarriesRole() {
        String token = provider.generateAccessToken("dr.kim", Role.DOCTOR);
        assertEquals(Role.DOCTOR, provider.extractRole(token));
    }

    @Test
    void roleSurvivesForEveryRoleValue() {
        for (Role role : Role.values()) {
            String token = provider.generateAccessToken("someone", role);
            assertEquals(role, provider.extractRole(token));
        }
    }

    @Test
    void accessTokenValidityIsEightHours() {
        assertEquals(28800L, provider.getAccessTokenValiditySeconds());
    }

    @Test
    void shortSecretIsRejectedAtStartup() {
        JwtTokenProvider weak = new JwtTokenProvider();
        ReflectionTestUtils.setField(weak, "secretKey", "tooshort");
        assertThrows(IllegalStateException.class, weak::init);
    }

    @Test
    void tamperedTokenFailsValidation() {
        // 예전엔 토큰 문자열 맨 끝 두 글자(서명 세그먼트의 꼬리)를 "xy" 로 바꿔치기했다.
        // 이게 구조적으로 불안정하다: base64 는 3바이트를 4글자에 담으므로, 인코딩
        // 경계에 걸리는 마지막 한두 글자는 실제 정보를 6비트보다 적게 담고 나머지는
        // 항상 0인 패딩 비트다. 서명 검증은 이 세그먼트를 "디코딩한 뒤" 바이트를
        // 비교하므로, 하필 패딩 비트만 건드리는 대체 문자를 고르면 디코딩 결과가
        // 원래와 완전히 같아져 서명이 여전히 유효하다고 통과해 버린다. 토큰마다
        // (iat/exp 타임스탬프가 달라) 서명 바이트가 매번 다르니 이 경계에 걸릴지는
        // 실행마다 달라져 이 테스트가 간헐적으로 실패했다.
        //
        // payload 세그먼트를 건드리면 이 문제가 없다: JWT 서명은 "디코딩된 바이트"가
        // 아니라 header.payload 를 이룬 base64url 문자열 그 자체(원문 바이트)에 대해
        // 계산된다. 그 문자열에서 단 한 글자라도 달라지면 서명 검증 쪽에서 다시 계산하는
        // HMAC 입력이 항상 달라지므로, 재계산된 서명이 원래 서명과 우연히 같아질 확률은
        // (경계 문제가 아니라) 암호학적 충돌 확률 수준(HS512 기준 사실상 0)이다 —
        // 실행마다 결과가 갈릴 여지가 없다.
        String token = provider.generateAccessToken("dr.kim", Role.DOCTOR);
        String[] parts = token.split("\\.");
        assertEquals(3, parts.length, "JWT 는 header.payload.signature 세 세그먼트여야 한다");

        String payload = parts[1];
        char lastChar = payload.charAt(payload.length() - 1);
        char replacement = (lastChar == 'A') ? 'B' : 'A';
        String tamperedPayload = payload.substring(0, payload.length() - 1) + replacement;
        String tampered = parts[0] + "." + tamperedPayload + "." + parts[2];

        assertFalse(provider.validateToken(tampered));
    }
}
