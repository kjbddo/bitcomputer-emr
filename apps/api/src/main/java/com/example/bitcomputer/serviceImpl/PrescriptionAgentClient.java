package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.model.SavePrescriptionFeedbackRequestDTO;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Python(FastAPI) 의 prescription_api 서비스를 호출하는 HTTP 클라이언트.
 *
 * <p>처방 추천(/recommend) 은 Spring 을 거치지 않고 validation-agent 가 직접 호출하므로,
 * 이 클라이언트는 처방 피드백을 Arango 그래프에 적재하는 경로만 담당한다.
 */
@Component
public class PrescriptionAgentClient {

    private final RestTemplate restTemplate;

    @Value("${ai.prescription-agent.base-url:http://localhost:8001}")
    private String baseUrl;

    @Value("${ai.prescription-agent.feedback-path:/api/agent/prescription/feedback}")
    private String feedbackPath;

    public PrescriptionAgentClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public void saveFeedbackToGraph(SavePrescriptionFeedbackRequestDTO request) {
        String url = baseUrl + feedbackPath;
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));

        List<Map<String, Object>> feedbackItems = new ArrayList<>();
        for (SavePrescriptionFeedbackRequestDTO.FeedbackItem item : request.getFeedbackItems()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("rank", item.getRank());
            row.put("prescription_id", item.getPrescriptionId());
            row.put("prescription_code", item.getPrescriptionCode());
            row.put("prescription_name", item.getPrescriptionName());
            row.put("confidence_score", item.getConfidenceScore());
            row.put("reason", item.getReason());
            row.put("status", item.getStatus());
            feedbackItems.add(row);
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("history_id", request.getHistoryId());
        payload.put("history_diagnose_id", request.getHistoryDiagnoseId());
        payload.put("feedback_items", feedbackItems);

        try {
            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(payload, headers);
            ResponseEntity<Map> response = restTemplate.exchange(
                    url, HttpMethod.POST, entity, Map.class);
            if (!response.getStatusCode().is2xxSuccessful()) {
                throw new IllegalStateException(
                        "그래프 피드백 API 비정상 응답 status=" + response.getStatusCode());
            }
        } catch (RestClientException e) {
            throw new IllegalStateException("그래프 피드백 API 호출 실패: " + e.getMessage(), e);
        }
    }
}
