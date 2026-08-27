package com.example.bitcomputer.exception;

/** 이미 존재하는 부서명으로 생성·수정하려 할 때. 409 로 매핑된다. */
public class DuplicateDeptNameException extends RuntimeException {
    public DuplicateDeptNameException(String message) {
        super(message);
    }
}
