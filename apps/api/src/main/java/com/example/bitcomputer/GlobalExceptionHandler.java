package com.example.bitcomputer;

import jakarta.persistence.EntityNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(EntityNotFoundException.class)
    public ResponseEntity<String> handleEntityNotFound(EntityNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ex.getMessage());
    }

    // ResponseStatusException 은 RuntimeException 의 하위 타입이라, 이 핸들러가 없으면
    // 아래 handleRuntimeException 이 먼저 잡아 던지는 쪽이 의도한 상태 코드(예: 404, 400)를
    // 뭉개고 무조건 500 으로 응답해 버린다. Spring 은 예외 타입 계층에서 가장 구체적인
    // @ExceptionHandler 를 고르므로, 이 메서드가 handleRuntimeException 보다 우선 적용된다.
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<String> handleResponseStatusException(ResponseStatusException ex) {
        return ResponseEntity.status(ex.getStatusCode()).body(ex.getReason());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<String> handleGeneralException(Exception ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body("An error occurred: " + ex.getMessage());
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<String> handleAccessDeniedException(AccessDeniedException ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(ex.getMessage());
    }

    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<String> handleRuntimeException(RuntimeException ex) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(ex.getMessage());
    }

    // IllegalArgumentException 은 컨트롤러가 로컬에서 잡지 않은 온갖 입력 검증 오류에서도
    // 던져진다(예: HistoryDiagnoseServiceImpl/HistoryDiseaseServiceImpl 의 "이미 존재함",
    // "id가 유효하지 않음" 등 — 해당 컨트롤러들은 try/catch 가 없어 여기까지 올라온다).
    // 401 로 응답하면 프론트엔드의 401 → /login 리다이렉트 인터셉터가 이를 "로그아웃"으로
    // 오인해, 단순 입력 오류가 강제 로그아웃처럼 보인다(I5). 400 이 실제 성격에 맞다.
    // UserController 는 자체 @ExceptionHandler(IllegalArgumentException.class) 로 409 를
    // 응답하므로(중복 아이디는 진짜 충돌이다) 이 전역 핸들러보다 우선 적용돼 영향이 없다.
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> handleIllegalArgumentException(IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(ex.getMessage());
    }
}
