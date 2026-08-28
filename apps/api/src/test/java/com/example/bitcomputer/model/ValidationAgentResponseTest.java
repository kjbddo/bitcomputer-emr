package com.example.bitcomputer.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ValidationAgentResponseTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * ValidationEventProcessor 는 응답을 이 DTO 로 역직렬화한 뒤 다시 직렬화해
     * resultJson 에 저장한다. DTO 가 모르는 필드는 그 왕복에서 사라진다.
     * 그래서 이 테스트는 "필드가 있다"가 아니라 "왕복이 보존한다"를 단언한다.
     */
    @Test
    void roundTripPreservesLlmStatusAndReasoningTrace() throws Exception {
        String upstream = "{"
                + "\"overallStatus\": \"PASS\","
                + "\"summary\": \"이상 없음\","
                + "\"reason\": \"규칙 통과\","
                + "\"llmStatus\": \"fallback\","
                + "\"reasoningTrace\": [{\"action\": \"Disease Validator\", \"source\": \"fallback\"}],"
                + "\"recommendedPrescriptions\": [{\"name\": \"약\"}],"
                + "\"validation\": {\"k\": \"v\"}"
                + "}";

        ValidationAgentResponse parsed = objectMapper.readValue(upstream, ValidationAgentResponse.class);
        String roundTripped = objectMapper.writeValueAsString(parsed);

        assertThat(parsed.getLlmStatus()).isEqualTo("fallback");
        assertThat(roundTripped).contains("\"llmStatus\":\"fallback\"");
        assertThat(roundTripped).contains("\"source\":\"fallback\"");
        assertThat(roundTripped).contains("recommendedPrescriptions");
        assertThat(roundTripped).contains("\"reason\"");
        assertThat(roundTripped).contains("\"validation\"");
    }

    /**
     * 상류가 필드를 안 줬을 때 "모델이 돌았다"로 기울면 안 된다.
     * 파이썬 쪽 기본값과 같은 방향(fail-closed)으로 맞춘다.
     */
    @Test
    void missingLlmStatusDoesNotClaimRealModel() throws Exception {
        ValidationAgentResponse parsed = objectMapper.readValue(
                "{\"overallStatus\":\"PASS\",\"summary\":\"s\"}", ValidationAgentResponse.class);

        // isNotEqualTo("real") 만으로는 부족하다: @Builder.Default 가 사라지면
        // 필드는 "real" 이 아닌 null 로 떨어지는데, 그래도 이 단언은 통과해 버려서
        // 기본값이 조용히 사라지는 걸 못 잡는다. 파이썬 쪽 기본값과 동일한 값까지 확인한다.
        assertThat(parsed.getLlmStatus()).isEqualTo("fallback");
    }
}
