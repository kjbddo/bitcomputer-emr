package com.example.bitcomputer.service;

import com.example.bitcomputer.model.DeptDTO;

import java.util.List;

public interface DeptService {
    List<DeptDTO> findAll();
    DeptDTO create(String name);
    DeptDTO rename(int id, String name);
}
