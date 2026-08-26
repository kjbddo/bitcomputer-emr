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
        log.setActorUsername(auth != null ? String.valueOf(auth.getName()) : "anonymous");
        log.setActorRole(resolveRole(auth));
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

    private String resolveRole(Authentication auth) {
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
