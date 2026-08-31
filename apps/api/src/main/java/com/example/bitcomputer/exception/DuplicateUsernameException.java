package com.example.bitcomputer.exception;

/**
 * 회원가입 시 이미 존재하는 사용자 ID로 가입을 시도했을 때 던진다.
 * 실제 충돌(409)이므로 로그인 실패(401)와는 구분되는 별도 타입으로 둔다.
 */
public class DuplicateUsernameException extends RuntimeException {
    public DuplicateUsernameException(String message) {
        super(message);
    }
}
