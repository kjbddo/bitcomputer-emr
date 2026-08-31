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

    /**
     * prescription_api 자신의 {@code llmStatus}. 위 {@code llmStatus}
     * (validation-agent 가 자기 결정을 어떻게 냈는지)와는 다른 서비스, 다른
     * 축이므로 병합하지 않는다 — 처방 표의 모델 출처 배지가 읽어야 하는 값은
     * 이쪽이다(F-H3).
     *
     * <p>{@code @Builder.Default} 를 붙이지 않는다. 위 {@code llmStatus} 와
     * 달리 이 값은 "처방 후보 조회를 아예 안 했다" 라는 상태가 실재하고, 그때
     * "폴백으로 만들었다"고 말하면 하지 않은 주장을 하게 된다(GC-2). null 이
     * 그대로 웹까지 가고, 웹은 그것을 "출처 미확인"으로 렌더한다(GC-3).
     */
    private String prescriptionLlmStatus;

    /**
     * prescription_api 의 신기능 금기 관문
     * (services/prescription/renal_gate.py): {status, renalStatus, renalEvidence,
     * items[], undeterminedReason}.
     *
     * <p>{@code status} 는 {@code warn} / {@code clear} / {@code unknown} 셋이고
     * 이 셋은 서로 무너지지 않는다. {@code clear} 는 "이 표의 범위 안에서 해당
     * 없음" 이지 "안전함" 이 아니다 — 표는 좁고 부분적이며, 그 범위를 문장으로
     * 들고 다니는 것은 {@code items[].evidence} 다. 화면이 evidence 를 버리고
     * outcome 만 쓰면 범위가 사라진다.
     *
     * <p>기본값을 두지 않는다. 관문을 돌리지 못한 것은 {@code clear} 가 아니라
     * "확인 못 함" 이고, 그 둘이 같은 값으로 나가면 이 관문이 있는 이유가
     * 사라진다(GC-3, 설계 §3.3).
     */
    private Map<String, Object> prescriptionRenalGate;

    @JsonProperty("shouldNotifyDoctor")
    private Boolean shouldNotifyDoctor;

    @JsonProperty("shouldBlockAutoPrescription")
    private Boolean shouldBlockAutoPrescription;
}
