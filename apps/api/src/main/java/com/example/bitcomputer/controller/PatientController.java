    package com.example.bitcomputer.controller;

import com.example.bitcomputer.Repository.EmployeeRepository;
import com.example.bitcomputer.annotation.Audited;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.model.PatientDTO;
import com.example.bitcomputer.model.HistoryDTO;
import com.example.bitcomputer.model.WriteHistoryDTO;
import com.example.bitcomputer.service.AuditService;
import com.example.bitcomputer.service.HistoryService;
import com.example.bitcomputer.service.PatientService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.*;
import org.springframework.format.annotation.DateTimeFormat;

import java.util.Map;

import java.time.LocalDate;
import java.util.List;
import java.util.LinkedHashMap;

@RestController
@RequestMapping("/api/patients")
public class PatientController {

    private final PatientService patientService;
    private final HistoryService historyService;
    private final EmployeeRepository employeeRepository;

    public PatientController(PatientService patientService, HistoryService historyService,
                             EmployeeRepository employeeRepository) {
        this.patientService = patientService;
        this.historyService = historyService;
        this.employeeRepository = employeeRepository;
    }

    @Audited(action = "PATIENT_CREATE")
    @PostMapping("/get_patient_id")
    public ResponseEntity<Map<String, Integer>> createPatient(@RequestBody PatientDTO request) {
        PatientDTO created = patientService.createPatient(request);
        Map<String, Integer> responseBody = Map.of("patientId", created.getId());
        return ResponseEntity.status(HttpStatus.CREATED).body(responseBody);
    }

    // 경로 변수 이름을 "patientId"로 명시한다 - AuditInterceptor 가 targetPatientId 를
    // 뽑을 때 이 이름만 본다(관리자 뮤테이션의 "{id}"와 겹치지 않도록 I1 에서 정리).
    // URL 자체(/api/patients/42)는 바뀌지 않는다 - 템플릿 변수 이름은 클라이언트에
    // 노출되지 않는 내부 구현 디테일이다.
    @Audited(action = "PATIENT_VIEW")
    @GetMapping("/{patientId}")
    public ResponseEntity<PatientDTO> getPatient(@PathVariable int patientId) {
        PatientDTO patient = patientService.searchPatientById(patientId);
        return ResponseEntity.ok(patient);
    }

    @PostMapping("/search_history/{id}")
    public ResponseEntity<Map<String, Object>> searchHistory(@PathVariable("id") int employeeId, 
    @RequestParam("patientId") int patientId, 
    @RequestParam(value = "startDate", required = false) @DateTimeFormat(pattern = "yyyy-MM-dd") LocalDate startDate,
    @RequestParam(value = "endDate", required = false) @DateTimeFormat(pattern = "yyyy-MM-dd") LocalDate endDate) {
        if (startDate != null && endDate != null && startDate.isAfter(endDate)) {
            return ResponseEntity.badRequest().build();
        }

        Map<String, Object> response = historyService.searchHistory(patientId, startDate, endDate);
        return ResponseEntity.ok(response);
    }

    @PostMapping("/search_patient/{id}")
    public ResponseEntity<PatientDTO> searchPatient(@PathVariable int id) {
        PatientDTO patient = patientService.searchPatientById(id);
        return ResponseEntity.ok(patient);
    }

    @PostMapping("/update_history/{id}")
    public ResponseEntity<HistoryDTO> updateHistory(@PathVariable int id, @RequestBody WriteHistoryDTO request) {
        HistoryDTO history = historyService.updateHistory(id, request);
        return ResponseEntity.ok(history);
    }

    @GetMapping("/get_all")
    public ResponseEntity<List<PatientDTO>> getAllPatients() {
        List<PatientDTO> patients = patientService.getAllPatients();
        return ResponseEntity.ok(patients);
    }

    @GetMapping("/doctors")
    public ResponseEntity<List<Map<String, Object>>> getDoctors() {
        List<Map<String, Object>> doctors = employeeRepository.findAll().stream()
                .filter(employee -> employee.getRole() == Role.DOCTOR)
                .map(employee -> {
                    Map<String, Object> payload = new LinkedHashMap<>();
                    payload.put("id", employee.getId());
                    payload.put("name", employee.getName());
                    payload.put("deptId", employee.getDeptId());
                    payload.put("username", employee.getUsername());
                    return payload;
                })
                .toList();
        return ResponseEntity.ok(doctors);
    }

    @GetMapping("/get_role")
    public ResponseEntity<Role> getRole() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        Employee employee = employeeRepository.findByUsername(AuditService.resolveActorUsername(authentication));
        if (employee == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }

        return ResponseEntity.ok(employee.getRole());
    }

    @GetMapping("/get_me")
    public ResponseEntity<Map<String, Object>> getMe() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        Employee employee = employeeRepository.findByUsername(AuditService.resolveActorUsername(authentication));
        if (employee == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", employee.getId());
        payload.put("name", employee.getName());
        payload.put("deptId", employee.getDeptId());
        payload.put("role", employee.getRole());
        payload.put("username", employee.getUsername());
        return ResponseEntity.ok(payload);
    }
}

