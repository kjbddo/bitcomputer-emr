package com.example.bitcomputer.service;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.entity.AccessAuditLog;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
public class AuditService {

    public static final String GRANTED = "GRANTED";
    public static final String DENIED = "DENIED";

    private final AccessAuditLogRepository repository;

    public AuditService(AccessAuditLogRepository repository) {
        this.repository = repository;
    }

    public void record(String action, Integer patientId, Integer historyId,
                       String ip, String outcome, String detail) {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();

        AccessAuditLog log = new AccessAuditLog();
        log.setOccurredAt(LocalDateTime.now());
        log.setActorUsername(resolveActorUsername(auth));
        log.setActorRole(resolveActorRole(auth));
        log.setAction(action);
        log.setTargetPatientId(patientId);
        log.setTargetHistoryId(historyId);
        log.setRequestIp(ip);
        log.setOutcome(outcome);
        log.setDetail(detail);

        repository.save(log);
    }

    public String clientIp(HttpServletRequest request) {
        String forwarded = request.getHeader("X-Forwarded-For");
        if (forwarded != null && !forwarded.isBlank()) {
            return forwarded.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }

    /**
     * record(...) 저장이 실패했을 때(제약 위반, DB 다운 등) 호출자가 fail-open 으로
     * 요청은 통과시키면서도 ERROR 로그에 "누가" 했는지는 남길 수 있도록, 실제 DB 행에
     * 쓰는 것과 같은 방식으로 행위자를 도출하는 로직을 정적 메서드로 공개한다.
     * AuditInterceptor / RestAccessDeniedHandler 가 그 catch 블록에서 이 두 메서드를
     * 그대로 사용한다 — ROLE_ 접두어 제거 규칙을 세 군데서 따로 구현하지 않기 위함이다.
     */
    public static String resolveActorUsername(Authentication auth) {
        return auth != null ? String.valueOf(auth.getName()) : "anonymous";
    }

    public static String resolveActorRole(Authentication auth) {
        if (auth == null) {
            return "ANONYMOUS";
        }
        return auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(a -> a.startsWith("ROLE_"))
                .map(a -> a.substring("ROLE_".length()))
                .findFirst()
                .orElse("UNKNOWN");
    }
}
