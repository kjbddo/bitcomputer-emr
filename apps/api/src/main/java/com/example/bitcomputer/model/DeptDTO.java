package com.example.bitcomputer.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class DeptDTO {
    private int id;
    private String dept;
    /** 이 부서에 소속된 직원 수. 어느 부서가 실제로 쓰이는지 화면에서 보이게 한다. */
    private long employeeCount;
}
