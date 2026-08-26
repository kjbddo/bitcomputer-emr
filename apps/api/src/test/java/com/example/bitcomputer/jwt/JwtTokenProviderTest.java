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
        String token = provider.generateAccessToken("dr.kim", Role.DOCTOR);
        String tampered = token.substring(0, token.length() - 2) + "xy";
        assertFalse(provider.validateToken(tampered));
    }
}
