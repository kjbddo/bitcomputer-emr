package com.example.bitcomputer.config;

import com.example.bitcomputer.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * 권한 거부를 403 으로 응답하면서 감사 로그에 남긴다.
 * 접근 "시도" 자체가 감사 대상이다.
 */
@Component
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private static final Logger log = LoggerFactory.getLogger(RestAccessDeniedHandler.class);

    private final AuditService auditService;

    public RestAccessDeniedHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException {
        // 감사 로그 기록 실패가 의도한 403 응답을 (핸들러 밖으로 예외가 새어나가
        // GlobalExceptionHandler 가 500 으로 잡는 식으로) 가려서는 안 된다.
        // fail-open: 실패는 ERROR 로 남기고, 그래도 403 은 정상적으로 응답한다.
        //
        // CsrfException(MissingCsrfTokenException 포함)은 RBAC 권한 거부와 다른 사건이다
        // — 진짜 권한 침해 시도와 토큰 만료 같은 일상적인 잡음이 같은 ACCESS_DENIED 로
        // 섞이면 감사 로그로 둘을 구분할 수 없다(I2). action 을 분리해 기록한다.
        //
        // 행위자(누가)는 record(...) 안에서 SecurityContextHolder 로부터 도출되므로,
        // record(...) 가 실패했을 때 남기는 이 catch 블록의 로그에도 같은 방식으로
        // 직접 도출해 둔다 — "누가" 가 빠진 감사 폴백 로그는 사고 재구성에 쓸모가 없다.
        // getAuthentication() 이 null 이어도 resolveActorUsername/Role 은 예외 없이
        // "anonymous"/"ANONYMOUS" 를 돌려주므로, fail-open 로깅 자체가 NPE 로
        // 죽는 일은 없다. (SecurityConfig 가 jwtAuthenticationFilter 를 CsrfFilter 보다
        // 앞에 두므로, CSRF 로 거부된 요청도 쿠키에 유효한 JWT 가 있었다면 여기서
        // "anonymous" 가 아니라 실제 행위자를 얻는다.)
        String action = accessDeniedException instanceof CsrfException ? "CSRF_REJECTED" : "ACCESS_DENIED";
        String clientIp = auditService.clientIp(request);
        String detail = request.getMethod() + " " + request.getRequestURI();
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        String actorUsername = AuditService.resolveActorUsername(authentication);
        String actorRole = AuditService.resolveActorRole(authentication);
        try {
            auditService.record(
                    action,
                    null,
                    null,
                    clientIp,
                    AuditService.DENIED,
                    detail);
        } catch (Exception ex) {
            log.error("감사 로그 기록 실패(fail-open, 403 응답은 계속 진행): actor={}, actorRole={}, "
                            + "action={}, patientId=null, historyId=null, ip={}, outcome={}, "
                            + "detail={}",
                    actorUsername, actorRole, action, clientIp, AuditService.DENIED, detail, ex);
        }

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
    }
}
