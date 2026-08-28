package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.Repository.DeptRepository;
import com.example.bitcomputer.Repository.EmployeeRepository;
import com.example.bitcomputer.entity.Dept;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.exception.DuplicateDeptNameException;
import com.example.bitcomputer.model.DeptDTO;
import com.example.bitcomputer.service.DeptService;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class DeptServiceImpl implements DeptService {

    private final DeptRepository deptRepository;
    private final EmployeeRepository employeeRepository;

    public DeptServiceImpl(DeptRepository deptRepository, EmployeeRepository employeeRepository) {
        this.deptRepository = deptRepository;
        this.employeeRepository = employeeRepository;
    }

    @Override
    @Transactional(readOnly = true)
    public List<DeptDTO> findAll() {
        Map<Integer, Long> counts = employeeRepository.findAll().stream()
                .collect(Collectors.groupingBy(Employee::getDeptId, Collectors.counting()));

        return deptRepository.findAll().stream()
                .sorted(Comparator.comparingInt(Dept::getId))
                .map(d -> new DeptDTO(d.getId(), d.getDept(), counts.getOrDefault(d.getId(), 0L)))
                .collect(Collectors.toList());
    }

    @Override
    @Transactional
    public DeptDTO create(String name) {
        String trimmed = requireNonBlank(name);
        requireNameAvailable(trimmed, null);

        Dept saved = deptRepository.save(new Dept(0, trimmed));
        return new DeptDTO(saved.getId(), saved.getDept(), 0L);
    }

    @Override
    @Transactional
    public DeptDTO rename(int id, String name) {
        String trimmed = requireNonBlank(name);

        Dept dept = deptRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("부서를 찾을 수 없습니다. id=" + id));

        requireNameAvailable(trimmed, id);

        dept.setDept(trimmed);
        deptRepository.save(dept);

        long count = employeeRepository.findAll().stream()
                .filter(e -> e.getDeptId() == id)
                .count();
        return new DeptDTO(dept.getId(), dept.getDept(), count);
    }

    private String requireNonBlank(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("부서명은 비어 있을 수 없습니다.");
        }
        return name.trim();
    }

    /** excludeId 가 null 이 아니면 그 부서는 중복 검사에서 제외한다(자기 자신 이름 유지 허용). */
    private void requireNameAvailable(String name, Integer excludeId) {
        boolean taken = deptRepository.findAll().stream()
                .filter(d -> excludeId == null || d.getId() != excludeId)
                .anyMatch(d -> d.getDept().equalsIgnoreCase(name));
        if (taken) {
            throw new DuplicateDeptNameException("이미 존재하는 부서명입니다: " + name);
        }
    }
}
