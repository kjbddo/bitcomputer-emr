package com.example.bitcomputer.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class ValidationAgentResponse {
    private String overallStatus;
    private String summary;
    private String reason;
    private List<Map<String, Object>> recommendedPrescriptions;
    private Map<String, Object> validation;
    private List<Map<String, Object>> reasoningTrace;
    private List<Map<String, Object>> checks;
    private List<Map<String, Object>> suspectedIssues;
    private List<String> suggestedReviewItems;
    private List<Map<String, Object>> candidatePrescriptions;

    // 상류가 이 필드를 안 주면 "모델 미사용" 쪽으로만 틀린다.
    // 파이썬 모델도 같은 기본값이다(services/validation-agent/app/models.py).
    @Builder.Default
    private String llmStatus = "fallback";

    @JsonProperty("shouldNotifyDoctor")
    private Boolean shouldNotifyDoctor;

    @JsonProperty("shouldBlockAutoPrescription")
    private Boolean shouldBlockAutoPrescription;
}
