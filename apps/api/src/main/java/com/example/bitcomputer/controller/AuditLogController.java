package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.AccessAuditLogRepository;
import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 감사 로그 조회. SecurityConfig 에서 SUPER_USER 전용으로 묶여 있다. */
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
            @RequestParam(defaultValue = "50") int size) {
        return ResponseEntity.ok(
                repository.findAllByOrderByOccurredAtDesc(PageRequest.of(page, Math.min(size, 200))));
    }
}
