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

    /**
     * validation-agent 자기 자신의 검증: {status, checks[], skippedReason}.
     * checks[].target 은 항상 "response" 다 — "prescription[N]" 은 절대 만들지
     * 않는다(services/validation-agent/app/verification.py). 항목 단위 배지는
     * 아래 prescriptionVerification 을 읽어야 한다.
     */
    private Map<String, Object> verification;

    /**
     * prescription_api 자신의 항목 단위 검증. checks[].target 이 "prescription[N]"
     * 인 유일한 출처다(services/prescription/verification.py). 위 verification
     * (validation-agent 자신의 판정) 과는 다른 서비스, 다른 판정이므로 병합하지
     * 않는다(최종 리뷰 C1).
     */
    private Map<String, Object> prescriptionVerification;

    @JsonProperty("shouldNotifyDoctor")
    private Boolean shouldNotifyDoctor;

    @JsonProperty("shouldBlockAutoPrescription")
    private Boolean shouldBlockAutoPrescription;
}
