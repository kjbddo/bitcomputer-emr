package com.example.bitcomputer.Repository;

import com.example.bitcomputer.entity.AccessAuditLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccessAuditLogRepository extends JpaRepository<AccessAuditLog, Long> {
    Page<AccessAuditLog> findAllByOrderByOccurredAtDesc(Pageable pageable);
}
