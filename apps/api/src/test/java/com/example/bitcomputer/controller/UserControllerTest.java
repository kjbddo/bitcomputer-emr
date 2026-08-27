package com.example.bitcomputer.controller;

import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.exception.DuplicateUsernameException;
import com.example.bitcomputer.exception.InvalidCredentialsException;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import com.example.bitcomputer.jwt.TokenInfo;
import com.example.bitcomputer.model.LoginRequestDTO;
import com.example.bitcomputer.model.UserRegisterDTO;
import com.example.bitcomputer.service.UserService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Duration;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@ExtendWith(MockitoExtension.class)
class UserControllerTest {

    MockMvc mockMvc;

    ObjectMapper objectMapper;

    @Mock
    UserService userService;

    @Mock
    JwtTokenProvider jwtTokenProvider;

    @Mock
    CookieFactory cookieFactory;

    @InjectMocks
    UserController userController;

    @BeforeEach
    void setup() {
        objectMapper = new ObjectMapper();
        mockMvc = MockMvcBuilders.standaloneSetup(userController)
                .setControllerAdvice(new com.example.bitcomputer.GlobalExceptionHandler())
                .build();
    }

    @Nested
    @DisplayName("POST /api/user/register")
    class Register {
        @Test
        @DisplayName("성공 시 201 Created")
        void register_success() throws Exception {
            doNothing().when(userService).registerUser(any(UserRegisterDTO.class));
            UserRegisterDTO dto = new UserRegisterDTO();
            dto.setName("n"); dto.setDeptId(1); dto.setRole("r"); dto.setUsername("u"); dto.setPassword("p");
            mockMvc.perform(post("/api/user/register")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(dto)))
                    .andExpect(status().isCreated());
        }

        @Test
        @DisplayName("중복 사용자 시 409 Conflict")
        void register_conflict() throws Exception {
            doThrow(new DuplicateUsernameException("Username already exists")).when(userService).registerUser(any(UserRegisterDTO.class));
            UserRegisterDTO dto = new UserRegisterDTO();
            dto.setName("n"); dto.setDeptId(1); dto.setRole("r"); dto.setUsername("u"); dto.setPassword("p");
            mockMvc.perform(post("/api/user/register")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(dto)))
                    .andExpect(status().isConflict());
        }
    }

    @Nested
    @DisplayName("POST /api/user/login")
    class Login {
        @Test
        @DisplayName("정상 로그인 시 200 OK + HttpOnly 쿠키, 본문에는 토큰 없음")
        void login_success() throws Exception {
            TokenInfo token = TokenInfo.builder().grantType("Bearer").accessToken("a").refreshToken("r").build();
            when(userService.loginUser(any(LoginRequestDTO.class))).thenReturn(token);
            when(jwtTokenProvider.getAccessTokenValiditySeconds()).thenReturn(28800L);
            ResponseCookie cookie = ResponseCookie.from(CookieFactory.ACCESS_TOKEN_COOKIE, "a")
                    .httpOnly(true)
                    .secure(false)
                    .sameSite("Lax")
                    .path("/")
                    .maxAge(Duration.ofSeconds(28800L))
                    .build();
            when(cookieFactory.accessTokenCookie(eq("a"), eq(28800L))).thenReturn(cookie);

            LoginRequestDTO dto = new LoginRequestDTO();
            dto.setUsername("u"); dto.setPassword("p");
            mockMvc.perform(post("/api/user/login")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(dto)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.grantType").value("Bearer"))
                    .andExpect(jsonPath("$.accessToken").doesNotExist())
                    .andExpect(jsonPath("$.refreshToken").doesNotExist())
                    .andExpect(header().exists("Set-Cookie"))
                    .andExpect(header().string("Set-Cookie",
                            org.hamcrest.Matchers.allOf(
                                    org.hamcrest.Matchers.containsString("access_token=a"),
                                    org.hamcrest.Matchers.containsString("HttpOnly"),
                                    org.hamcrest.Matchers.containsString("SameSite=Lax"))));
        }

        @Test
        @DisplayName("인증 실패 시 401 Unauthorized, 사용자 존재 여부는 노출하지 않음")
        void login_unauthorized() throws Exception {
            when(userService.loginUser(any(LoginRequestDTO.class)))
                    .thenThrow(new InvalidCredentialsException("Invalid username or password"));
            LoginRequestDTO dto = new LoginRequestDTO();
            dto.setUsername("u"); dto.setPassword("bad");
            mockMvc.perform(post("/api/user/login")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(dto)))
                    .andExpect(status().isUnauthorized())
                    .andExpect(content().string("Invalid username or password"));
        }

        @Test
        @DisplayName("존재하지 않는 사용자도 동일한 401 메시지(사용자 존재 여부 비노출)")
        void login_unknown_user_same_message_as_wrong_password() throws Exception {
            when(userService.loginUser(any(LoginRequestDTO.class)))
                    .thenThrow(new InvalidCredentialsException("Invalid username or password"));
            LoginRequestDTO dto = new LoginRequestDTO();
            dto.setUsername("nosuchuser"); dto.setPassword("wrong");
            mockMvc.perform(post("/api/user/login")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(dto)))
                    .andExpect(status().isUnauthorized())
                    .andExpect(content().string("Invalid username or password"));
        }
    }

    @Nested
    @DisplayName("POST /api/user/logout")
    class Logout {

        private ResponseCookie expiredCookie() {
            return ResponseCookie.from(CookieFactory.ACCESS_TOKEN_COOKIE, "")
                    .httpOnly(true)
                    .secure(false)
                    .sameSite("Lax")
                    .path("/")
                    .maxAge(Duration.ZERO)
                    .build();
        }

        @Test
        @DisplayName("쿠키가 있고 유효하면 200 OK + 만료 쿠키")
        void logout_success() throws Exception {
            doNothing().when(userService).logoutUser(any());
            when(jwtTokenProvider.validateToken(eq("token"))).thenReturn(true);
            when(cookieFactory.expiredAccessTokenCookie()).thenReturn(expiredCookie());

            mockMvc.perform(post("/api/user/logout")
                            .cookie(new jakarta.servlet.http.Cookie(CookieFactory.ACCESS_TOKEN_COOKIE, "token")))
                    .andExpect(status().isOk())
                    .andExpect(header().string("Set-Cookie",
                            org.hamcrest.Matchers.containsString("Max-Age=0")));
            verify(userService).logoutUser("token");
        }

        @Test
        @DisplayName("쿠키가 없어도 200 OK, 서비스는 호출하지 않음")
        void logout_no_cookie_still_ok() throws Exception {
            when(cookieFactory.expiredAccessTokenCookie()).thenReturn(expiredCookie());

            mockMvc.perform(post("/api/user/logout"))
                    .andExpect(status().isOk())
                    .andExpect(header().exists("Set-Cookie"));
            verify(userService, never()).logoutUser(any());
        }

        @Test
        @DisplayName("쿠키의 토큰이 유효하지 않아도 200 OK, 서비스는 호출하지 않음")
        void logout_invalid_token_still_ok() throws Exception {
            when(jwtTokenProvider.validateToken(eq("bad"))).thenReturn(false);
            when(cookieFactory.expiredAccessTokenCookie()).thenReturn(expiredCookie());

            mockMvc.perform(post("/api/user/logout")
                            .cookie(new jakarta.servlet.http.Cookie(CookieFactory.ACCESS_TOKEN_COOKIE, "bad")))
                    .andExpect(status().isOk());
            verify(userService, never()).logoutUser(any());
        }
    }
}
