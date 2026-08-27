package com.example.bitcomputer.config;

import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseCookie;

import static org.junit.jupiter.api.Assertions.*;

class CookieFactoryTest {

    @Test
    void accessTokenCookieIsHttpOnly() {
        ResponseCookie cookie = new CookieFactory(false, "local").accessTokenCookie("tok", 28800L);
        assertTrue(cookie.isHttpOnly());
    }

    @Test
    void accessTokenCookieUsesLaxSameSite() {
        ResponseCookie cookie = new CookieFactory(false, "local").accessTokenCookie("tok", 28800L);
        assertEquals("Lax", cookie.getSameSite());
    }

    @Test
    void accessTokenCookieCarriesValueAndMaxAge() {
        ResponseCookie cookie = new CookieFactory(false, "local").accessTokenCookie("tok", 28800L);
        assertEquals("access_token", cookie.getName());
        assertEquals("tok", cookie.getValue());
        assertEquals(28800L, cookie.getMaxAge().getSeconds());
    }

    @Test
    void secureFlagFollowsConfiguration() {
        assertFalse(new CookieFactory(false, "local").accessTokenCookie("tok", 1L).isSecure());
        assertTrue(new CookieFactory(true, "local").accessTokenCookie("tok", 1L).isSecure());
    }

    @Test
    void expiredCookieHasZeroMaxAgeAndEmptyValue() {
        ResponseCookie cookie = new CookieFactory(false, "local").expiredAccessTokenCookie();
        assertEquals(0L, cookie.getMaxAge().getSeconds());
        assertEquals("", cookie.getValue());
    }

    @Test
    void warnsWhenInsecureAndProfileIsNotLocalLike() {
        assertTrue(CookieFactory.isInsecureCookieInDeployment(false, "docker"));
        assertTrue(CookieFactory.isInsecureCookieInDeployment(false, "prod,docker"));
    }

    @Test
    void doesNotWarnWhenSecureRegardlessOfProfile() {
        assertFalse(CookieFactory.isInsecureCookieInDeployment(true, "docker"));
    }

    @Test
    void doesNotWarnForLocalOrDevProfiles() {
        assertFalse(CookieFactory.isInsecureCookieInDeployment(false, "local"));
        assertFalse(CookieFactory.isInsecureCookieInDeployment(false, "dev"));
        assertFalse(CookieFactory.isInsecureCookieInDeployment(false, "development"));
        assertFalse(CookieFactory.isInsecureCookieInDeployment(false, "LOCAL"));
    }

    @Test
    void doesNotWarnWhenActiveProfilesIsBlank() {
        assertFalse(CookieFactory.isInsecureCookieInDeployment(false, ""));
        assertFalse(CookieFactory.isInsecureCookieInDeployment(false, null));
    }
}
