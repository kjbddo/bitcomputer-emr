package com.example.bitcomputer.config;

import com.example.bitcomputer.annotation.AuditPatientAccess;
import com.example.bitcomputer.service.AuditService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class AuditInterceptor implements HandlerInterceptor {

    private static final Logger log = LoggerFactory.getLogger(AuditInterceptor.class);

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

        // 감사 로그 기록 실패(제약 위반, DB 다운 등)가 진료 행위 자체를 막아서는
        // 안 된다 — 병원 EMR 에서 감사 DB 의 일시적 장애 때문에 의사가 차트를
        // 못 보는 상황은 감사 로그 유실보다 훨씬 나쁘다. 여기서는 실패를 삼키고
        // ERROR 로 남긴 뒤(사고 재구성에 필요한 행위자/행동/대상/결과는 로그
        // 메시지에 담는다) 요청은 그대로 통과시킨다(fail-open).
        //
        // 행위자(누가)는 record(...) 안에서 SecurityContextHolder 로부터 도출되므로,
        // record(...) 가 실패했을 때 남기는 이 catch 블록의 로그에도 같은 방식으로
        // 직접 도출해 둔다 — "누가" 가 빠진 감사 폴백 로그는 사고 재구성에 쓸모가
        // 없다. try 진입 전에 미리 읽어 두는 이유는, 실패 이후 시점에는 인증
        // 컨텍스트가 이미 정리됐을 수도 있기 때문이다.
        String action = annotation.action();
        Integer patientId = parsePathVariable(request, "patientId", "id");
        Integer historyId = parsePathVariable(request, "historyId");
        String clientIp = auditService.clientIp(request);
        String detail = request.getMethod() + " " + request.getRequestURI();
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        String actorUsername = AuditService.resolveActorUsername(authentication);
        String actorRole = AuditService.resolveActorRole(authentication);
        try {
            auditService.record(action, patientId, historyId, clientIp, AuditService.GRANTED, detail);
        } catch (Exception ex) {
            log.error("감사 로그 기록 실패(fail-open, 요청은 계속 진행): actor={}, actorRole={}, "
                            + "action={}, patientId={}, historyId={}, ip={}, outcome={}, detail={}",
                    actorUsername, actorRole, action, patientId, historyId, clientIp,
                    AuditService.GRANTED, detail, ex);
        }
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
