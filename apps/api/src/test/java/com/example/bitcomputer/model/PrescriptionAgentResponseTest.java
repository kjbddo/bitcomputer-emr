package com.example.bitcomputer.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * F-M6: 이 DTO 는 {@code @JsonIgnoreProperties(ignoreUnknown = true)} 이므로
 * 선언되지 않은 필드는 역직렬화에서 조용히 사라진다. prescription_api 는
 * {@code engineStatus}/{@code llmStatus}/{@code verification} 을 모두 응답에
 * 싣는데(services/prescription/prescription_api.py 의
 * PrescriptionRecommendResponse), 이 DTO 는 셋 중 어느 것도 선언하지 않아
 * 동기 처방 경로에서 출처와 검증이 통째로 없어졌다.
 *
 * <p>필드 존재가 아니라 "상류가 준 값이 왕복에서 살아남는가"를 단언한다 —
 * 필드만 선언하고 setter 가 값을 버려도 전자는 통과한다.
 */
class PrescriptionAgentResponseTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void roundTripPreservesProvenanceFields() throws Exception {
        String upstream = "{"
                + "\"prescriptions\":[{\"rank\":1,\"name\":\"약1\",\"prescription_code\":\"C1\","
                + "\"dosage\":\"미기재\",\"reason\":\"근거\",\"confidence_score\":0.9}],"
                + "\"used_arango_top_rx\":true,\"arango_top_rx_count\":7,"
                + "\"engineStatus\":\"real\","
                + "\"llmStatus\":\"stub\","
                + "\"verification\":{\"status\":\"flagged\",\"checks\":["
                + "{\"id\":\"code_in_candidates\",\"target\":\"prescription[1]\","
                + "\"outcome\":\"flagged\",\"evidence\":\"코드 'Z99' 가 후보 3건 중 없음\"}],"
                + "\"skippedReason\":null}"
                + "}";

        PrescriptionAgentResponse parsed =
                objectMapper.readValue(upstream, PrescriptionAgentResponse.class);
        String roundTripped = objectMapper.writeValueAsString(parsed);

        assertThat(parsed.getLlmStatus()).isEqualTo("stub");
        assertThat(parsed.getEngineStatus()).isEqualTo("real");
        assertThat(parsed.getVerification()).isNotNull();

        assertThat(roundTripped).contains("\"llmStatus\":\"stub\"");
        assertThat(roundTripped).contains("\"engineStatus\":\"real\"");
        // 중첩 checks 의 원소까지 살아남아야 한다. 껍데기만 왕복해도 통과하는
        // 단언(키 이름만 확인)으로는 실제로 잃기 쉬운 것을 못 잡는다.
        assertThat(roundTripped).contains("\"target\":\"prescription[1]\"");
        assertThat(roundTripped).contains("Z99");
    }

    /**
     * 상류가 llmStatus 를 안 주면 "모델이 돌았다"로 기울면 안 된다.
     * 파이썬 쪽은 이 필드에 기본값을 두지 않으므로(빠뜨리면 응답 생성 자체가
     * 실패한다), 여기 도달한 null 은 "상류가 이 계약을 안 지켰다"는 뜻이다.
     * 그 경우에도 "real" 로 새면 안 된다.
     */
    @Test
    void missingProvenanceFieldsAreNullNotReal() throws Exception {
        PrescriptionAgentResponse parsed =
                objectMapper.readValue("{\"prescriptions\":[]}", PrescriptionAgentResponse.class);

        assertThat(parsed.getLlmStatus()).isNull();
        assertThat(parsed.getEngineStatus()).isNull();
        assertThat(parsed.getVerification()).isNull();
    }
}
