package com.example.bitcomputer;

import jakarta.persistence.EntityNotFoundException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    private static final String GENERIC_ERROR_MESSAGE =
            "요청을 처리하는 중 오류가 발생했습니다.";

    @ExceptionHandler(EntityNotFoundException.class)
    public ResponseEntity<String> handleEntityNotFound(EntityNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ex.getMessage());
    }

    @ExceptionHandler(com.example.bitcomputer.exception.DuplicateDeptNameException.class)
    public ResponseEntity<String> handleDuplicateDeptName(
            com.example.bitcomputer.exception.DuplicateDeptNameException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(ex.getMessage());
    }

    // NoResourceFoundException 은 RuntimeException 의 하위 타입이라(ErrorResponseException
    // 경유), 이 핸들러가 없으면 아래 handleRuntimeException/handleGeneralException 이
    // 먼저 잡아 매핑되지 않은 모든 경로를 무조건 500 으로 응답해 버린다. 원래 Spring
    // 이 던지는 상태 그대로(404 Not Found) 응답하도록 명시적으로 처리한다.
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<String> handleNoResourceFound(NoResourceFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body("리소스를 찾을 수 없습니다.");
    }

    // ResponseStatusException 은 RuntimeException 의 하위 타입이라, 이 핸들러가 없으면
    // 아래 handleRuntimeException 이 먼저 잡아 던지는 쪽이 의도한 상태 코드(예: 404, 400)를
    // 뭉개고 무조건 500 으로 응답해 버린다. Spring 은 예외 타입 계층에서 가장 구체적인
    // @ExceptionHandler 를 고르므로, 이 메서드가 handleRuntimeException 보다 우선 적용된다.
    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<String> handleResponseStatusException(ResponseStatusException ex) {
        return ResponseEntity.status(ex.getStatusCode()).body(ex.getReason());
    }

    // DataIntegrityViolationException(제약 조건 위반 등)도 RuntimeException 의 하위
    // 타입이다 — 이 핸들러가 없으면 handleRuntimeException 이 잡아 원본 SQL 문,
    // 테이블/컬럼/제약조건 이름이 그대로 응답 본문에 실려 나간다(정보 노출).
    // 전체 예외는 서버 로그에만 남기고, 클라이언트에는 안전한 일반 메시지만 준다.
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<String> handleDataIntegrityViolation(DataIntegrityViolationException ex) {
        log.error("데이터 무결성 제약 위반", ex);
        return ResponseEntity.status(HttpStatus.CONFLICT).body(GENERIC_ERROR_MESSAGE);
    }

    // M9: 요청 본문이 JSON 파싱조차 안 되는 경우(비어 있음, 문법 오류 등)
    // HttpMessageNotReadableException 이 던져진다. 이것도 RuntimeException 의
    // 하위 타입이라 이 핸들러가 없으면 handleRuntimeException 이 잡아 500 으로
    // 응답한다 - 클라이언트 입력 문제인데 서버 오류로 보인다. ex.getMessage() 는
    // Jackson 파서의 내부 위치 정보까지 담고 있어 그대로 노출하지 않는다.
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<String> handleHttpMessageNotReadable(HttpMessageNotReadableException ex) {
        log.warn("요청 본문을 읽을 수 없음", ex);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("요청 본문을 읽을 수 없습니다.");
    }

    // M9: 경로 변수가 기대한 타입(예: 숫자)이 아닐 때(PUT /api/admin/depts/abc 등)
    // MethodArgumentTypeMismatchException 이 던져진다. 마찬가지로
    // RuntimeException 하위 타입이라 이 핸들러가 없으면 500 으로 응답한다.
    // ex.getMessage() 는 대상 타입/클래스 이름 등 내부 정보를 담을 수 있어
    // 일반 메시지만 내려준다.
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<String> handleMethodArgumentTypeMismatch(MethodArgumentTypeMismatchException ex) {
        log.warn("요청 파라미터 타입 불일치", ex);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("요청 파라미터 형식이 올바르지 않습니다.");
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<String> handleAccessDeniedException(AccessDeniedException ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(ex.getMessage());
    }

    // RuntimeException.getMessage() 는 여기 잡히는 하위 타입에 따라 드라이버/라이브러리
    // 내부 메시지(쿼리, 스택 일부 등)를 포함할 수 있다 — 그대로 응답에 실으면 정보
    // 노출로 이어진다. 전체 내용은 ERROR 로 서버에만 남기고, 클라이언트에는 일반
    // 메시지만 내려준다.
    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<String> handleRuntimeException(RuntimeException ex) {
        log.error("처리되지 않은 RuntimeException", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(GENERIC_ERROR_MESSAGE);
    }

    // Exception 최상위 캐치-올. 마찬가지로 ex.getMessage() 를 그대로 내려주면
    // 무엇이 올라오든(체크 예외 포함) 내부 정보가 노출될 수 있다.
    @ExceptionHandler(Exception.class)
    public ResponseEntity<String> handleGeneralException(Exception ex) {
        log.error("처리되지 않은 예외", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(GENERIC_ERROR_MESSAGE);
    }

    // IllegalArgumentException 은 컨트롤러가 로컬에서 잡지 않은 온갖 입력 검증 오류에서도
    // 던져진다(예: HistoryDiagnoseServiceImpl/HistoryDiseaseServiceImpl 의 "이미 존재함",
    // "id가 유효하지 않음", UserServiceImpl.registerUser 의 "존재하지 않는 부서" 등 —
    // 해당 컨트롤러들은 try/catch 가 없어 여기까지 올라온다).
    // 401 로 응답하면 프론트엔드의 401 → /login 리다이렉트 인터셉터가 이를 "로그아웃"으로
    // 오인해, 단순 입력 오류가 강제 로그아웃처럼 보인다(I5). 400 이 실제 성격에 맞다.
    // 회원가입 아이디 중복(DuplicateUsernameException)과 로그인 인증 실패
    // (InvalidCredentialsException)는 UserController 자체 @ExceptionHandler 로
    // 각각 409/401 을 응답하므로 이 전역 핸들러보다 우선 적용돼 영향이 없다.
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> handleIllegalArgumentException(IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(ex.getMessage());
    }
}
