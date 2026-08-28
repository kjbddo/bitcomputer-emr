package com.example.bitcomputer.entity;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

@Entity
@Table(name = "employee")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;
    
    @Column(name = "name", nullable = false)
    private String name;
    
    @Column(name = "dept_id", nullable = false)
    private int deptId;
    
    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false)
    private Role role;
    
    @Column(name = "username", nullable = false, unique = true)
    private String username;
    
    // C1: 이 엔티티가 컨트롤러 응답에 그대로 직렬화되는 경로가 있다
    // (AdminController.getAllEmployees). WRITE_ONLY 로 직렬화(응답)에서는
    // 제외하고 역직렬화(요청 바인딩)에서는 계속 받도록 한다 — 다만 이 엔티티를
    // @RequestBody 로 직접 받는 컨트롤러는 현재 없으므로(회원가입/직원 생성은
    // 모두 별도 DTO 를 거친다) 실질적으로는 응답에서만 영향이 있다.
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @Column(name = "password", nullable = false)
    private String password;
    
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "dept_id", insertable = false, updatable = false)
    @JsonIgnore
    private Dept dept;
}