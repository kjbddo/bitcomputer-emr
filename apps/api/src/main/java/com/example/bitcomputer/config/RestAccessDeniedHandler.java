package com.example.bitcomputer.config;

import com.example.bitcomputer.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * 권한 거부를 403 으로 응답하면서 감사 로그에 남긴다.
 * 접근 "시도" 자체가 감사 대상이다.
 */
@Component
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private final AuditService auditService;

    public RestAccessDeniedHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
                       AccessDeniedException accessDeniedException) throws IOException {
        auditService.record(
                "ACCESS_DENIED",
                null,
                null,
                auditService.clientIp(request),
                AuditService.DENIED,
                request.getMethod() + " " + request.getRequestURI());

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
    }
}
