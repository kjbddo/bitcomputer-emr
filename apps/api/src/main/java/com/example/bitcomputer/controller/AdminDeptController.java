package com.example.bitcomputer.controller;

import com.example.bitcomputer.model.DeptCreateRequestDTO;
import com.example.bitcomputer.model.DeptDTO;
import com.example.bitcomputer.service.DeptService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 부서 생성·수정. SecurityConfig 에서 /api/admin/** 가 SUPER_USER 전용으로 묶여 있다. */
@RestController
@RequestMapping("/api/admin/depts")
public class AdminDeptController {

    private final DeptService deptService;

    public AdminDeptController(DeptService deptService) {
        this.deptService = deptService;
    }

    @PostMapping
    public ResponseEntity<DeptDTO> create(@RequestBody DeptCreateRequestDTO request) {
        DeptDTO created = deptService.create(request.getDept());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @PutMapping("/{id}")
    public ResponseEntity<DeptDTO> rename(@PathVariable int id,
                                          @RequestBody DeptCreateRequestDTO request) {
        return ResponseEntity.ok(deptService.rename(id, request.getDept()));
    }
}
