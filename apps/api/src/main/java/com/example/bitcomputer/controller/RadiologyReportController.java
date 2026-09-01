package com.example.bitcomputer.controller;

import com.example.bitcomputer.config.AiFeatures;
import com.example.bitcomputer.model.RadiologyAnalysisResponseDTO;
import com.example.bitcomputer.model.RadiologyReportRequestDTO;
import com.example.bitcomputer.service.RadiologyReportService;
import com.example.bitcomputer.util.ImageStorageUtil;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDate;
import java.util.Date;
import java.util.Map;

@RestController
@RequestMapping("/api/radiology")
public class RadiologyReportController {

    private final RadiologyReportService radiologyReportService;
    private final ImageStorageUtil imageStorageUtil;
    private final AiFeatures aiFeatures;

    public RadiologyReportController(
            RadiologyReportService radiologyReportService,
            ImageStorageUtil imageStorageUtil,
            AiFeatures aiFeatures) {
        this.radiologyReportService = radiologyReportService;
        this.imageStorageUtil = imageStorageUtil;
        this.aiFeatures = aiFeatures;
    }

    @PostMapping("/report")
    public ResponseEntity<RadiologyAnalysisResponseDTO> processRadiologyReport(
            @RequestBody RadiologyReportRequestDTO request) {
        try {
            RadiologyAnalysisResponseDTO response = radiologyReportService.processRadiologyReport(request);
            return ResponseEntity.ok(response);
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }

    /**
     * 이미지 업로드 및 AI 분석 통합 API
     * 
     * @param file 업로드된 이미지 파일
     * @param patientId 환자 ID
     * @param employeeId 근무자 ID
     * @param deptId 부서 ID
     * @param symptomDetail 증상 상세
     * @param memo 메모
     * @param entryDate 등록일자 (yyyy-MM-dd)
     * @param view 촬영 방향 (AP 또는 PA)
     * @return AI 분석 결과
     */
    @PostMapping(value = "/upload-and-analyze", consumes = "multipart/form-data")
    public ResponseEntity<?> uploadAndAnalyze(
            @RequestParam("file") MultipartFile file,
            @RequestParam("patientId") int patientId,
            @RequestParam("employeeId") int employeeId,
            @RequestParam("deptId") int deptId,
            @RequestParam(value = "symptomDetail", required = false) String symptomDetail,
            @RequestParam(value = "memo", required = false) String memo,
            @RequestParam(value = "view", required = false) String view,
            @RequestParam("entryDate") @DateTimeFormat(pattern = "yyyy-MM-dd") LocalDate entryDate) {
        
        // AI 없는 배포(DR)면 아무것도 하기 전에 끊는다.
        //
        // **여기여야 한다.** 이 메서드는 아래에서 순서대로 (2) 판독 요청을 DB 에
        // 저장하고 (3) 업로드 이미지를 디스크에 쓴 뒤 (6) 에서야 엔진을 부른다.
        // 게이트가 엔진 쪽에만 있으면 그 둘이 이미 일어난 뒤에 503 이 나가, DR 에서
        // 버튼을 누를 때마다 고아 `pending` 레코드와 이미지가 쌓인다. 실제로 그렇게
        // 쌓이는 것을 확인했다(2026-09-01 DR 스택 검증).
        //
        // 엔진 쪽 게이트(RadiologyReportServiceImpl.callConfiguredEngine)는 그대로
        // 둔다. 다른 진입점(POST /report)이 그 경로를 직접 쓰고, 그쪽은 앞선 쓰기가
        // 없어 그 자리가 맞다.
        aiFeatures.requireEnabled();

        try {
            // 1. 이미지 파일 검증
            if (file == null || file.isEmpty()) {
                return ResponseEntity.badRequest()
                        .body(Map.of("error", "이미지 파일이 필요합니다."));
            }
            
            // 파일 확장자 확인 (JPG, JPEG, PNG, DICOM만 허용)
            String fileName = file.getOriginalFilename();
            if (fileName == null || fileName.isEmpty()) {
                return ResponseEntity.badRequest()
                        .body(Map.of("error", "파일명이 없습니다."));
            }
            
            String lowerFileName = fileName.toLowerCase();
            boolean isValidExtension = lowerFileName.endsWith(".jpg") ||
                    lowerFileName.endsWith(".jpeg") ||
                    lowerFileName.endsWith(".png") ||
                    lowerFileName.endsWith(".dcm") ||
                    lowerFileName.endsWith(".dicom");
            
            if (!isValidExtension) {
                return ResponseEntity.badRequest()
                        .body(Map.of("error", "JPG, JPEG, PNG, DICOM 파일만 업로드 가능합니다."));
            }
            
            // 2. 영상판독 요청을 먼저 DB에 저장하여 radiologyRequestId 생성
            // 임시 경로로 RadiologyReport 생성
            RadiologyReportRequestDTO tempRequest = new RadiologyReportRequestDTO();
            tempRequest.setRadiologyRequestId(0);
            tempRequest.setPatientId(patientId);
            tempRequest.setEmployeeId(employeeId);
            tempRequest.setDeptId(deptId);
            tempRequest.setSymptomDetail(symptomDetail);
            tempRequest.setMemo(memo);
            tempRequest.setEntryDate(entryDate);
            tempRequest.setDetailImageAddress("temp/temp_" + java.util.UUID.randomUUID().toString()); // 임시 경로
            tempRequest.setView(normalizeView(view));
            
            // 영상판독 요청 저장하여 radiologyRequestId 받기
            int radiologyRequestId = radiologyReportService.createRadiologyReportRequest(tempRequest);
            
            // 3. radiologyRequestId로 폴더를 만들어 이미지 저장 (영상판독 요청별 고유 폴더)
            String folderId = String.valueOf(radiologyRequestId);
            String imageRelativePath = imageStorageUtil.saveImage(file, folderId, "original");
            
            // 4. RadiologyReportRequestDTO 생성 (실제 이미지 경로 포함)
            RadiologyReportRequestDTO request = new RadiologyReportRequestDTO();
            request.setRadiologyRequestId(radiologyRequestId);
            request.setPatientId(patientId);
            request.setEmployeeId(employeeId);
            request.setDeptId(deptId);
            request.setSymptomDetail(symptomDetail);
            request.setMemo(memo);
            request.setEntryDate(entryDate);
            request.setDetailImageAddress(imageRelativePath);
            request.setView(normalizeView(view));
            
            // 5. 이미지 경로 업데이트 (DB 업데이트)
            radiologyReportService.updateImagePath(radiologyRequestId, imageRelativePath);
            
            // 6. AI 분석 요청
            RadiologyAnalysisResponseDTO response = radiologyReportService.processRadiologyReport(request);
            
            // 7. 응답 반환 (오버레이 이미지 URL 포함)
            return ResponseEntity.ok(response);
            
        } catch (org.springframework.web.server.ResponseStatusException e) {
            // ResponseStatusException은 메시지를 포함하여 반환
            return ResponseEntity.status(e.getStatusCode())
                    .body(Map.of("error", e.getReason() != null ? e.getReason() : "처리 중 오류가 발생했습니다."));
        } catch (Exception e) {
            e.printStackTrace();
            String errorMessage = e.getMessage() != null ? e.getMessage() : "처리 중 오류가 발생했습니다.";
            if (e.getCause() != null) {
                errorMessage += " (" + e.getCause().getMessage() + ")";
            }
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", errorMessage));
        }
    }

    private String normalizeView(String view) {
        if (view == null || view.isBlank()) {
            return null;
        }
        String normalized = view.trim().toUpperCase();
        if (!"AP".equals(normalized) && !"PA".equals(normalized)) {
            throw new org.springframework.web.server.ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "view는 AP 또는 PA만 가능합니다.");
        }
        return normalized;
    }
}
