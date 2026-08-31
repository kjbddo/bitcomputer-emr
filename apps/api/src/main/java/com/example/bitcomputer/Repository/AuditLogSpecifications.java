package com.example.bitcomputer.Repository;

import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.jpa.domain.Specification;

import java.time.LocalDateTime;

/**
 * 감사 로그 필터 조합.
 *
 * 파라미터가 6개이고 조합이 자유로워 메서드 이름 기반 쿼리로는 감당되지 않는다.
 * 각 메서드는 값이 없으면 null 을 반환하고, and() 가 null 을 무시한다.
 */
public final class AuditLogSpecifications {

    private AuditLogSpecifications() {
    }

    public static Specification<AccessAuditLog> actorUsernameContains(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String pattern = "%" + value.trim().toLowerCase() + "%";
        return (root, query, cb) -> cb.like(cb.lower(root.get("actorUsername")), pattern);
    }

    public static Specification<AccessAuditLog> targetPatientIdEquals(Integer value) {
        if (value == null) {
            return null;
        }
        return (root, query, cb) -> cb.equal(root.get("targetPatientId"), value);
    }

    public static Specification<AccessAuditLog> actionEquals(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return (root, query, cb) -> cb.equal(root.get("action"), value.trim());
    }

    public static Specification<AccessAuditLog> outcomeEquals(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return (root, query, cb) -> cb.equal(root.get("outcome"), value.trim());
    }

    public static Specification<AccessAuditLog> occurredFrom(LocalDateTime value) {
        if (value == null) {
            return null;
        }
        return (root, query, cb) -> cb.greaterThanOrEqualTo(root.get("occurredAt"), value);
    }

    public static Specification<AccessAuditLog> occurredTo(LocalDateTime value) {
        if (value == null) {
            return null;
        }
        return (root, query, cb) -> cb.lessThanOrEqualTo(root.get("occurredAt"), value);
    }
}
