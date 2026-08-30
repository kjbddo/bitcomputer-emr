package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.Repository.HistoryDiagnoseRepository;
import com.example.bitcomputer.Repository.HistoryDiseaseRepository;
import com.example.bitcomputer.Repository.HistoryRepository;
import com.example.bitcomputer.Repository.PatientRepository;
import com.example.bitcomputer.Repository.PrescriptionFeedbackRepository;
import com.example.bitcomputer.Repository.RadiologyReportRepository;
import com.example.bitcomputer.Repository.ValidationJobRepository;
import com.example.bitcomputer.entity.History;
import com.example.bitcomputer.entity.HistoryDiagnose;
import com.example.bitcomputer.entity.HistoryDisease;
import com.example.bitcomputer.entity.Patient;
import com.example.bitcomputer.entity.PrescriptionFeedback;
import com.example.bitcomputer.entity.RadiologyReport;
import com.example.bitcomputer.entity.ValidationJob;
import com.example.bitcomputer.entity.ValidationJobStatus;
import com.example.bitcomputer.model.PrescriptionRecommendRequestDTO;
import com.example.bitcomputer.model.SavePrescriptionFeedbackRequestDTO;
import com.example.bitcomputer.model.ValidationJobStartResponseDTO;
import com.example.bitcomputer.service.AgentService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.EntityNotFoundException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
public class AgentServiceImpl implements AgentService {

    private final HistoryDiagnoseRepository historyDiagnoseRepository;
    private final HistoryRepository historyRepository;
    private final HistoryDiseaseRepository historyDiseaseRepository;
    private final PatientRepository patientRepository;
    private final PrescriptionFeedbackRepository prescriptionFeedbackRepository;
    private final RadiologyReportRepository radiologyReportRepository;
    private final ValidationJobRepository validationJobRepository;
    private final PrescriptionAgentClient prescriptionAgentClient;
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    @Value("${validation.rabbitmq.request-queue:validation.prescription.request}")
    private String validationRequestQueue;

    public AgentServiceImpl(
            HistoryDiagnoseRepository historyDiagnoseRepository,
            HistoryRepository historyRepository,
            HistoryDiseaseRepository historyDiseaseRepository,
            PatientRepository patientRepository,
            PrescriptionFeedbackRepository prescriptionFeedbackRepository,
            RadiologyReportRepository radiologyReportRepository,
            ValidationJobRepository validationJobRepository,
            ObjectMapper objectMapper,
            PrescriptionAgentClient prescriptionAgentClient,
            RabbitTemplate rabbitTemplate) {
        this.historyDiagnoseRepository = historyDiagnoseRepository;
        this.historyRepository = historyRepository;
        this.historyDiseaseRepository = historyDiseaseRepository;
        this.patientRepository = patientRepository;
        this.prescriptionFeedbackRepository = prescriptionFeedbackRepository;
        this.radiologyReportRepository = radiologyReportRepository;
        this.validationJobRepository = validationJobRepository;
        this.objectMapper = objectMapper;
        this.prescriptionAgentClient = prescriptionAgentClient;
        this.rabbitTemplate = rabbitTemplate;
    }

    @Override
    public ValidationJobStartResponseDTO recommendPrescription(PrescriptionRecommendRequestDTO request) {
        History currentHistory = resolveCurrentHistory(request);
        Patient patient = patientRepository.findById(currentHistory.getPatientId())
                .orElseThrow(() -> new EntityNotFoundException(
                        "Patient not found with id " + currentHistory.getPatientId()));
        String jobId = UUID.randomUUID().toString();
        Map<String, Object> payload = buildValidationJobPayload(jobId, currentHistory, patient, request);

        ValidationJob job = new ValidationJob();
        job.setJobId(jobId);
        job.setHistoryId(currentHistory.getId());
        job.setPatientId(currentHistory.getPatientId());
        job.setEmployeeId(currentHistory.getEmployeeId());
        job.setDeptId(currentHistory.getDeptId());
        job.setTriggerType("AI_PRESCRIPTION_RECOMMEND");
        job.setStatus(ValidationJobStatus.PENDING);
        job.setRequestPayloadJson(toJson(payload));
        validationJobRepository.save(job);

        rabbitTemplate.convertAndSend(validationRequestQueue, payload);
        log.info("AI 처방 추천/검증 job 발행 - jobId={} historyId={}", jobId, currentHistory.getId());

        return ValidationJobStartResponseDTO.builder()
                .jobId(jobId)
                .historyId(currentHistory.getId())
                .status(ValidationJobStatus.PENDING)
                .build();
    }

    private Map<String, Object> buildValidationJobPayload(
            String jobId,
            History history,
            Patient patient,
            PrescriptionRecommendRequestDTO request) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("jobId", jobId);
        payload.put("eventId", 0);
        payload.put("eventType", "AI_PRESCRIPTION_RECOMMEND");
        payload.put("triggerType", "AI_PRESCRIPTION_RECOMMEND");
        payload.put("historyId", history.getId());
        payload.put("patientId", history.getPatientId());
        payload.put("employeeId", history.getEmployeeId());
        payload.put("deptId", history.getDeptId());
        payload.put("symptoms", history.getSymptomDetail());
        payload.put("createdAt", LocalDateTime.now(ZoneId.of("Asia/Seoul")).toString());
        Map<String, Object> patientSummary = new LinkedHashMap<>();
        patientSummary.put("patientId", history.getPatientId());
        patientSummary.put("name", patient.getName());
        patientSummary.put("gender", patient.getGender());
        patientSummary.put("birth", patient.getBirth() != null ? patient.getBirth().toString() : "");
        patientSummary.put("visitNumber", patient.getVisitNumber() != null ? patient.getVisitNumber() : "");
        payload.put("patientSummary", patientSummary);
        payload.put("savedDiseases", toDiseaseRows(historyDiseaseRepository.findByHistoryId(history.getId()), request));
        payload.put("savedPrescriptions", toPrescriptionRows(historyDiagnoseRepository.findByHistoryId(history.getId())));
        payload.put("xrayInference", loadLatestXrayInference(history.getPatientId()));
        return payload;
    }

    private List<Map<String, Object>> toDiseaseRows(
            List<HistoryDisease> diseases,
            PrescriptionRecommendRequestDTO request) {
        List<Map<String, Object>> rows = diseases.stream()
                .map(disease -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("id", disease.getId());
                    row.put("code", disease.getCode());
                    row.put("name", disease.getName());
                    row.put("degree", disease.getDegree());
                    return row;
                })
                .collect(Collectors.toCollection(ArrayList::new));
        if (!rows.isEmpty() || request.getDiseaseCodes() == null) {
            return rows;
        }
        for (String code : request.getDiseaseCodes()) {
            if (code == null || code.isBlank()) {
                continue;
            }
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("code", code.trim());
            row.put("name", code.trim());
            row.put("degree", "");
            rows.add(row);
        }
        return rows;
    }

    private List<Map<String, Object>> toPrescriptionRows(List<HistoryDiagnose> diagnoses) {
        return diagnoses.stream()
                .map(diagnose -> {
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("id", diagnose.getId());
                    row.put("code", diagnose.getCode());
                    row.put("name", diagnose.getName());
                    row.put("dose", diagnose.getDose());
                    row.put("time", diagnose.getTime());
                    row.put("days", diagnose.getDays());
                    return row;
                })
                .toList();
    }

    private Map<String, Object> loadLatestXrayInference(int patientId) {
        return radiologyReportRepository
                .findFirstByPatientIdAndStatusOrderByEntryDateDescRadiologyRequestIdDesc(patientId, "completed")
                .map(this::toXrayInference)
                .orElse(null);
    }

    private Map<String, Object> toXrayInference(RadiologyReport report) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("radiologyRequestId", report.getRadiologyRequestId());
        out.put("result", report.getResult());
        out.put("predictedDiseases", parsePredictedDiseases(report.getSummary()));
        out.put("heatmapUrl", report.getImageUrl());
        out.put("status", report.getStatus());
        out.put("entryDate", report.getEntryDate());
        return out;
    }

    private Object parsePredictedDiseases(String summary) {
        if (summary == null || summary.isBlank()) {
            return List.of();
        }
        try {
            return objectMapper.readValue(summary, Object.class);
        } catch (Exception e) {
            return summary;
        }
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("validation job payload 직렬화 실패", e);
        }
    }

    @SuppressWarnings("unchecked")
    private History resolveCurrentHistory(PrescriptionRecommendRequestDTO request) {
        if (request.getHistoryId() != null) {
            return historyRepository.findById(request.getHistoryId())
                    .orElseThrow(() -> new EntityNotFoundException(
                            "History not found with id " + request.getHistoryId()));
        }
        if (request.getHistoryDiagnoseId() != null) {
            HistoryDiagnose hd = historyDiagnoseRepository.findById(request.getHistoryDiagnoseId())
                    .orElseThrow(() -> new EntityNotFoundException(
                            "HistoryDiagnose not found with id " + request.getHistoryDiagnoseId()));
            return historyRepository.findById(hd.getHistoryId())
                    .orElseThrow(() -> new EntityNotFoundException(
                            "History not found with id " + hd.getHistoryId()));
        }
        throw new IllegalArgumentException("history_id 또는 history_diagnose_id 중 하나는 필수입니다.");
    }

    @Override
    @org.springframework.transaction.annotation.Transactional
    public void savePrescriptionFeedback(SavePrescriptionFeedbackRequestDTO request) {
        if (request.getHistoryId() == null || request.getFeedbackItems() == null || request.getFeedbackItems().isEmpty()) {
            throw new IllegalArgumentException("historyId and feedbackItems are required");
        }

        boolean hasMissed = request.getFeedbackItems().stream().anyMatch(i -> "missed".equals(i.getStatus()));
        boolean hasAiStatuses = request.getFeedbackItems().stream()
                .anyMatch(i -> "accepted".equals(i.getStatus()) || "rejected".equals(i.getStatus()));

        // missed와 accepted/rejected는 서로를 지우지 않도록 분리 삭제
        if (hasMissed) {
            prescriptionFeedbackRepository.deleteMissedByHistoryId(request.getHistoryId());
        }
        if (hasAiStatuses) {
            prescriptionFeedbackRepository.deleteNonMissedByHistoryId(request.getHistoryId());
        }

        LocalDateTime now = LocalDateTime.now();
        List<PrescriptionFeedback> entities = request.getFeedbackItems().stream()
                .map(item -> {
                    PrescriptionFeedback fb = new PrescriptionFeedback();
                    fb.setHistoryId(request.getHistoryId());
                    fb.setHistoryDiagnoseId(request.getHistoryDiagnoseId());
                    fb.setRank(item.getRank());
                    fb.setPrescriptionId(item.getPrescriptionId());
                    fb.setPrescriptionCode(item.getPrescriptionCode());
                    fb.setPrescriptionName(item.getPrescriptionName());
                    fb.setConfidenceScore(item.getConfidenceScore());
                    fb.setReason(item.getReason());
                    fb.setStatus(item.getStatus());
                    fb.setCreatedAt(now);
                    return fb;
                })
                .collect(Collectors.toList());
        prescriptionFeedbackRepository.saveAll(entities);
        try {
            prescriptionAgentClient.saveFeedbackToGraph(request);
        } catch (Exception e) {
            // MySQL 저장 성공은 유지하고, 그래프 적재 실패는 경고로 남긴다.
            log.warn("Arango 처방 피드백 저장 실패: historyId={}, err={}", request.getHistoryId(), e.getMessage());
        }
        log.info("처방 피드백 저장: historyId={}, accepted={}, rejected={}, missed={}",
                request.getHistoryId(),
                entities.stream().filter(e -> "accepted".equals(e.getStatus())).count(),
                entities.stream().filter(e -> "rejected".equals(e.getStatus())).count(),
                entities.stream().filter(e -> "missed".equals(e.getStatus())).count());
    }
}
