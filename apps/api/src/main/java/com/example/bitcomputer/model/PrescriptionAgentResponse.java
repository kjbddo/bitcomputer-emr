package com.example.bitcomputer.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Python(FastAPI) prescription_api → Spring 응답 본문.
 *
 * <p>LLM 이 생성·검증한 처방 3건이 {@code prescriptions} 배열에 담긴다.
 * Python 쪽에서 {@code prescription_agent.parse_prescriptions_llm_response} 로
 * 스키마를 이미 검증하기 때문에, Spring 은 그대로 매핑만 하면 된다.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class PrescriptionAgentResponse {

    /** LLM 게이트웨이가 반환한 rank 1·2·3 처방 항목. 길이는 항상 3 이 보장됨(Python 검증). */
    private List<Item> prescriptions;

    /** Python 이 Arango 로 top_rx 를 보강했으면 true. */
    @JsonProperty("used_arango_top_rx")
    private Boolean usedArangoTopRx;

    /** Arango 에서 로드된 top_rx 행 수. */
    @JsonProperty("arango_top_rx_count")
    private Integer arangoTopRxCount;

    /** 상병 코호트 AQL 로 처방 통계를 병합했으면 true. */
    @JsonProperty("used_cohort_rx")
    private Boolean usedCohortRx;

    /** 코호트에서 가져온 처방 통계 행 수. */
    @JsonProperty("cohort_rx_count")
    private Integer cohortRxCount;

    /**
     * 추론 엔진이 실제 구현인지 대역인지. 설정이 아니라 실행 경로에서 나온다
     * (services/prescription/prescription_api.py).
     *
     * <p>기본값을 두지 않는다 — 상류가 안 주면 null 이고, null 은 "모른다"이지
     * "real"이 아니다(GC-3).
     */
    @JsonProperty("engineStatus")
    private String engineStatus;

    /**
     * 이 응답이 실제로 모델에서 나왔는지. {@code engineStatus} 와 다른 축이다.
     *
     * <p>파이썬 쪽은 이 필드에 기본값을 두지 않는다(빠뜨리면 응답 생성 자체가
     * 실패한다). 그러므로 여기 도달한 null 은 계약 위반 신호이며, 그때도
     * "real" 로 새면 안 된다.
     */
    @JsonProperty("llmStatus")
    private String llmStatus;

    /**
     * prescription_api 자신의 항목 단위 검증. {@code checks[].target} 이
     * {@code "prescription[N]"} 인 유일한 출처다
     * (services/prescription/verification.py).
     *
     * <p>기본값을 만들지 않는다 — 검증하지 않은 것이 검증된 것처럼 보이면
     * 이 필드가 존재할 이유가 사라진다.
     */
    @JsonProperty("verification")
    private Map<String, Object> verification;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Item {

        /** 1 ~ 3. */
        private int rank;

        /** top_rx 에 등장한 처방명 또는 처방코드 문자열. */
        private String name;

        /** top_rx 의 처방코드. 데이터가 없으면 "미기재". */
        @JsonProperty("prescription_code")
        private String prescriptionCode;

        /** 입력에 용량이 있으면 그대로, 없으면 "미기재". */
        private String dosage;

        /** 데이터 인용 + 짧은 임상/약리 보강(한국어). */
        private String reason;

        /** 모델/후처리 confidence (없으면 null). */
        @JsonProperty("confidence_score")
        private Double confidenceScore;
    }
}
