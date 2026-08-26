package com.example.bitcomputer.config;

import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseCookie;

import static org.junit.jupiter.api.Assertions.*;

class CookieFactoryTest {

    @Test
    void accessTokenCookieIsHttpOnly() {
        ResponseCookie cookie = new CookieFactory(false).accessTokenCookie("tok", 28800L);
        assertTrue(cookie.isHttpOnly());
    }

    @Test
    void accessTokenCookieUsesLaxSameSite() {
        ResponseCookie cookie = new CookieFactory(false).accessTokenCookie("tok", 28800L);
        assertEquals("Lax", cookie.getSameSite());
    }

    @Test
    void accessTokenCookieCarriesValueAndMaxAge() {
        ResponseCookie cookie = new CookieFactory(false).accessTokenCookie("tok", 28800L);
        assertEquals("access_token", cookie.getName());
        assertEquals("tok", cookie.getValue());
        assertEquals(28800L, cookie.getMaxAge().getSeconds());
    }

    @Test
    void secureFlagFollowsConfiguration() {
        assertFalse(new CookieFactory(false).accessTokenCookie("tok", 1L).isSecure());
        assertTrue(new CookieFactory(true).accessTokenCookie("tok", 1L).isSecure());
    }

    @Test
    void expiredCookieHasZeroMaxAgeAndEmptyValue() {
        ResponseCookie cookie = new CookieFactory(false).expiredAccessTokenCookie();
        assertEquals(0L, cookie.getMaxAge().getSeconds());
        assertEquals("", cookie.getValue());
    }
}
