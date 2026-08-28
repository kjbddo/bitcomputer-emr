package com.example.bitcomputer.config;

import com.example.bitcomputer.annotation.Audited;
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

    private static final String AUDIT_CONTEXT_ATTRIBUTE =
            AuditInterceptor.class.getName() + ".context";

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (!(handler instanceof HandlerMethod method)) {
            return true;
        }
        Audited annotation = method.getMethodAnnotation(Audited.class);
        if (annotation == null) {
            return true;
        }

        // preHandle 은 컨트롤러가 실행되기 "전"이라 요청이 실제로 통과했는지(2xx)
        // 아니면 거부/실패했는지(4xx/5xx)를 알 수 없다 — 여기서 바로 기록하면 401
        // 로 거부된 요청도 GRANTED 로 남는다(I1). 그래서 여기서는 필요한 값만
        // 모아 요청 속성에 담아 두고, 실제 기록은 응답 상태를 알 수 있는
        // afterCompletion 에서 한다.
        String action = annotation.action();
        // "patientId" 이름의 경로 변수만 본다("id" 는 더 이상 fallback 으로 보지
        // 않는다). 관리자 뮤테이션(PUT /api/admin/users/{id}/role,
        // PUT /api/admin/depts/{id})도 경로 변수 이름이 "id"라, 예전처럼 "id"를
        // 환자 ID 로도 취급하면 직원 ID·부서 ID 가 targetPatientId 컬럼에 잘못
        // 찍힌다. PatientController.getPatient 의 경로 변수를 "patientId"로 맞춰
        // 두었으므로 여기서는 정확한 이름 하나만 찾는다.
        Integer patientId = parsePathVariable(request, "patientId");
        Integer historyId = parsePathVariable(request, "historyId");
        String clientIp = auditService.clientIp(request);
        String detail = request.getMethod() + " " + request.getRequestURI();

        request.setAttribute(AUDIT_CONTEXT_ATTRIBUTE,
                new AuditContext(action, patientId, historyId, clientIp, detail));
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response,
                                Object handler, Exception ex) {
        AuditContext context = (AuditContext) request.getAttribute(AUDIT_CONTEXT_ATTRIBUTE);
        if (context == null) {
            return;
        }

        // 2xx/3xx 는 GRANTED, 그 외(4xx/5xx — 인증/권한 거부는 물론 서버 오류까지)는
        // DENIED 로 남긴다. 컨트롤러가 던진 예외는 GlobalExceptionHandler 가 이미
        // 상태 코드로 변환해 응답에 반영한 뒤이므로(그래서 이 시점의 ex 인자는
        // 사실상 항상 null 이다), response.getStatus() 하나만 보면 된다.
        String outcome = response.getStatus() < 400 ? AuditService.GRANTED : AuditService.DENIED;

        // 감사 로그 기록 실패(제약 위반, DB 다운 등)가 진료 행위 자체를 막아서는
        // 안 된다 — 병원 EMR 에서 감사 DB 의 일시적 장애 때문에 의사가 차트를
        // 못 보는 상황은 감사 로그 유실보다 훨씬 나쁘다. 여기서는 실패를 삼키고
        // ERROR 로 남긴 뒤(사고 재구성에 필요한 행위자/행동/대상/결과는 로그
        // 메시지에 담는다) 요청은 그대로 통과시킨다(fail-open).
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        String actorUsername = AuditService.resolveActorUsername(authentication);
        String actorRole = AuditService.resolveActorRole(authentication);
        try {
            auditService.record(context.action(), context.patientId(), context.historyId(),
                    context.clientIp(), outcome, context.detail());
        } catch (Exception recordEx) {
            log.error("감사 로그 기록 실패(fail-open, 요청은 계속 진행): actor={}, actorRole={}, "
                            + "action={}, patientId={}, historyId={}, ip={}, outcome={}, detail={}",
                    actorUsername, actorRole, context.action(), context.patientId(), context.historyId(),
                    context.clientIp(), outcome, context.detail(), recordEx);
        }
    }

    private record AuditContext(String action, Integer patientId, Integer historyId,
                                String clientIp, String detail) {
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
