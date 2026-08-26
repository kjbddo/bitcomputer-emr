package com.example.bitcomputer.entity;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * 환자 기록 접근 감사 로그.
 *
 * append-only 다. 수정·삭제 API 를 만들지 않는다.
 */
@Entity
@Table(name = "access_audit_log", indexes = {
        @Index(name = "idx_audit_occurred_at", columnList = "occurred_at"),
        @Index(name = "idx_audit_patient", columnList = "target_patient_id")
})
@Data
@NoArgsConstructor
@AllArgsConstructor
public class AccessAuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "occurred_at", nullable = false)
    private LocalDateTime occurredAt;

    @Column(name = "actor_username", nullable = false, length = 100)
    private String actorUsername;

    @Column(name = "actor_role", nullable = false, length = 30)
    private String actorRole;

    @Column(name = "action", nullable = false, length = 60)
    private String action;

    @Column(name = "target_patient_id")
    private Integer targetPatientId;

    @Column(name = "target_history_id")
    private Integer targetHistoryId;

    @Column(name = "request_ip", length = 64)
    private String requestIp;

    /** GRANTED | DENIED */
    @Column(name = "outcome", nullable = false, length = 16)
    private String outcome;

    @Column(name = "detail", columnDefinition = "TEXT")
    private String detail;
}
