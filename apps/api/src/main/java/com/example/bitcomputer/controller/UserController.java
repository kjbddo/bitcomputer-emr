package com.example.bitcomputer.controller;

import com.example.bitcomputer.config.CookieFactory;
import com.example.bitcomputer.exception.DuplicateUsernameException;
import com.example.bitcomputer.exception.InvalidCredentialsException;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import com.example.bitcomputer.jwt.TokenInfo;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import com.example.bitcomputer.service.UserService;
import com.example.bitcomputer.model.UserRegisterDTO;
import com.example.bitcomputer.model.LoginRequestDTO;

@RestController
@RequestMapping("/api/user")
public class UserController {

    private final UserService userService;
    private final JwtTokenProvider jwtTokenProvider;
    private final CookieFactory cookieFactory;

    public UserController(UserService userService, JwtTokenProvider jwtTokenProvider,
                          CookieFactory cookieFactory) {
        this.userService = userService;
        this.jwtTokenProvider = jwtTokenProvider;
        this.cookieFactory = cookieFactory;
    }

    // 회원가입 시 아이디 중복 = 진짜 충돌(409).
    @ExceptionHandler(DuplicateUsernameException.class)
    public ResponseEntity<String> handleDuplicateUsername(DuplicateUsernameException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(e.getMessage());
    }

    // 로그인 인증 실패 = 401. 사용자 부재/비밀번호 불일치를 구분하지 않는
    // 동일한 메시지만 내려준다(사용자 존재 여부 노출 금지).
    @ExceptionHandler(InvalidCredentialsException.class)
    public ResponseEntity<String> handleInvalidCredentials(InvalidCredentialsException e) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(e.getMessage());
    }

    @PostMapping("/register")
    public ResponseEntity<String> registerUser(@RequestBody UserRegisterDTO userRegisterDTO) {
        userService.registerUser(userRegisterDTO);
        return ResponseEntity.status(HttpStatus.CREATED).body("User registered successfully");
    }

    @PostMapping("/login")
    public ResponseEntity<TokenInfo> loginUser(@RequestBody LoginRequestDTO loginRequestDTO) {
        TokenInfo tokenInfo = userService.loginUser(loginRequestDTO);
        ResponseCookie cookie = cookieFactory.accessTokenCookie(
                tokenInfo.getAccessToken(), jwtTokenProvider.getAccessTokenValiditySeconds());
        // 응답 본문에서는 access token 을 제거한다. 쿠키로만 전달한다.
        TokenInfo body = TokenInfo.builder()
                .grantType(tokenInfo.getGrantType())
                .accessToken(null)
                .refreshToken(null)
                .build();
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(body);
    }

    @PostMapping("/logout")
    public ResponseEntity<String> logout(
            @CookieValue(value = CookieFactory.ACCESS_TOKEN_COOKIE, required = false) String token) {
        ResponseCookie expired = cookieFactory.expiredAccessTokenCookie();
        if (token != null && jwtTokenProvider.validateToken(token)) {
            userService.logoutUser(token);
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, expired.toString())
                .body("Logged out successfully");
    }
}
