package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.Repository.AuditLogSpecifications;
import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;

/**
 * 감사 로그 조회. SecurityConfig 에서 SUPER_USER 전용으로 묶여 있다.
 *
 * 이 엔드포인트에는 @AuditPatientAccess 를 붙이지 않는다. 감사 로그 조회를 감사 로그에
 * 남기면 조회할 때마다 행이 늘어 신호 대 잡음비가 나빠진다.
 */
@RestController
@RequestMapping("/api/audit")
public class AuditLogController {

    private final AccessAuditLogRepository repository;

    public AuditLogController(AccessAuditLogRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/logs")
    public ResponseEntity<Page<AccessAuditLog>> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "50") int size,
            @RequestParam(required = false) String actorUsername,
            @RequestParam(required = false) Integer targetPatientId,
            @RequestParam(required = false) String action,
            @RequestParam(required = false) String outcome,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam(required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to) {

        Specification<AccessAuditLog> spec = Specification
                .allOf(AuditLogSpecifications.actorUsernameContains(actorUsername),
                       AuditLogSpecifications.targetPatientIdEquals(targetPatientId),
                       AuditLogSpecifications.actionEquals(action),
                       AuditLogSpecifications.outcomeEquals(outcome),
                       AuditLogSpecifications.occurredFrom(from),
                       AuditLogSpecifications.occurredTo(to));

        PageRequest pageable = PageRequest.of(
                page, Math.min(size, 200), Sort.by(Sort.Direction.DESC, "occurredAt"));

        return ResponseEntity.ok(repository.findAll(spec, pageable));
    }
}
