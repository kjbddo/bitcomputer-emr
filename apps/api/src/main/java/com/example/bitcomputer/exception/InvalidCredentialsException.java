package com.example.bitcomputer.exception;

/**
 * 로그인 인증 실패(존재하지 않는 사용자, 비밀번호 불일치) 시 던진다.
 * 두 경우 모두 동일한 메시지/상태(401)로만 응답해야 한다 — 사용자 존재 여부를
 * 노출하지 않기 위함이다.
 */
public class InvalidCredentialsException extends RuntimeException {
    public InvalidCredentialsException(String message) {
        super(message);
    }
}
