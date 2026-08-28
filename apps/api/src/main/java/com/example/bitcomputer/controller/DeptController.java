package com.example.bitcomputer.controller;

import com.example.bitcomputer.model.DeptDTO;
import com.example.bitcomputer.service.DeptService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * 부서 목록 조회.
 *
 * SUPER_USER 전용인 /api/admin 밖에 두는 이유는 직원 추가 폼에서 부서를 고르려면
 * 목록이 필요하고, 부서명은 민감 정보가 아니기 때문이다. SecurityConfig 의
 * anyRequest() 규칙에 걸려 DEFAULT 를 제외한 인증된 역할이 읽을 수 있다.
 */
@RestController
@RequestMapping("/api/depts")
public class DeptController {

    private final DeptService deptService;

    public DeptController(DeptService deptService) {
        this.deptService = deptService;
    }

    @GetMapping
    public ResponseEntity<List<DeptDTO>> list() {
        return ResponseEntity.ok(deptService.findAll());
    }
}
