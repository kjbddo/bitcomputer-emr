package com.example.bitcomputer.config;

import com.example.bitcomputer.annotation.AuditPatientAccess;
import com.example.bitcomputer.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class AuditInterceptor implements HandlerInterceptor {

    private final AuditService auditService;

    public AuditInterceptor(AuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (!(handler instanceof HandlerMethod method)) {
            return true;
        }
        AuditPatientAccess annotation = method.getMethodAnnotation(AuditPatientAccess.class);
        if (annotation == null) {
            return true;
        }

        auditService.record(
                annotation.action(),
                parsePathVariable(request, "patientId", "id"),
                parsePathVariable(request, "historyId"),
                auditService.clientIp(request),
                AuditService.GRANTED,
                request.getMethod() + " " + request.getRequestURI());
        return true;
    }

    @SuppressWarnings("unchecked")
    private Integer parsePathVariable(HttpServletRequest request, String... names) {
        Object attr = request.getAttribute(
                org.springframework.web.servlet.HandlerMapping.URI_TEMPLATE_VARIABLES_ATTRIBUTE);
        if (!(attr instanceof java.util.Map<?, ?> vars)) {
            return null;
        }
        for (String name : names) {
            Object raw = vars.get(name);
            if (raw == null) {
                continue;
            }
            try {
                return Integer.valueOf(String.valueOf(raw));
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }
}
