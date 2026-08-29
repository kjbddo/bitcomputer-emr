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
        // 필드가 "있다"가 아니라 상류가 준 "값"이 왕복에서 살아남는지를 본다.
        // contains("recommendedPrescriptions") 같은 키 이름만 확인하는 단언은
        // setter 가 값을 버려도(예: 항상 null 로 덮어써도) 통과해버린다.
        assertThat(roundTripped).contains("\"reason\":\"규칙 통과\"");
        assertThat(roundTripped).contains("\"recommendedPrescriptions\":[{\"name\":\"약\"}]");
        assertThat(roundTripped).contains("\"validation\":{\"k\":\"v\"}");
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

    @Test
    void roundTripPreservesVerification() throws Exception {
        // 중첩 checks 를 비워 두면 껍데기만 살아남아도 통과한다. 실제로 잃기
        // 쉬운 것은 배열 안의 원소이므로 원소의 필드 값까지 단언한다.
        String upstream = "{"
                + "\"overallStatus\":\"PASS\",\"summary\":\"ok\","
                + "\"verification\":{\"status\":\"flagged\",\"checks\":["
                + "{\"id\":\"cited_pmid_in_evidence\",\"target\":\"response\","
                + "\"outcome\":\"flagged\",\"evidence\":\"조회 결과에 없는 PMID: 99999999\"}],"
                + "\"skippedReason\":null}"
                + "}";

        ValidationAgentResponse parsed =
                objectMapper.readValue(upstream, ValidationAgentResponse.class);
        String roundTripped = objectMapper.writeValueAsString(parsed);

        assertThat(parsed.getVerification()).isNotNull();
        assertThat(roundTripped).contains("\"status\":\"flagged\"");
        assertThat(roundTripped).contains("\"id\":\"cited_pmid_in_evidence\"");
        assertThat(roundTripped).contains("\"outcome\":\"flagged\"");
        assertThat(roundTripped).contains("99999999");
    }

    @Test
    void missingVerificationIsNull() throws Exception {
        ValidationAgentResponse parsed = objectMapper.readValue(
                "{\"overallStatus\":\"PASS\",\"summary\":\"s\"}", ValidationAgentResponse.class);

        assertThat(parsed.getVerification()).isNull();
    }

    /**
     * 최종 리뷰 C1: prescription_api 자신의 항목 단위 검증(target="prescription[N]")
     * 이 이 DTO 를 거치며 사라지면 웹의 처방 항목 배지가 영구히 미검증으로 남는다.
     * DTO 가 모르는 필드는 왕복에서 조용히 사라지므로(@JsonIgnoreProperties), 필드
     * 존재가 아니라 값이 왕복에서 살아남는지를 단언한다.
     */
    @Test
    void roundTripPreservesPrescriptionVerification() throws Exception {
        String upstream = "{"
                + "\"overallStatus\":\"PASS\",\"summary\":\"ok\","
                + "\"verification\":{\"status\":\"passed\",\"checks\":["
                + "{\"id\":\"trace_step_has_observation\",\"target\":\"response\","
                + "\"outcome\":\"ok\",\"evidence\":\"4개 스텝 모두 관측값 있음\"}],"
                + "\"skippedReason\":null},"
                + "\"prescriptionVerification\":{\"status\":\"flagged\",\"checks\":["
                + "{\"id\":\"code_in_candidates\",\"target\":\"prescription[1]\","
                + "\"outcome\":\"flagged\",\"evidence\":\"코드 'Z99' 가 후보 3건 중 없음\"}],"
                + "\"skippedReason\":null}"
                + "}";

        ValidationAgentResponse parsed =
                objectMapper.readValue(upstream, ValidationAgentResponse.class);
        String roundTripped = objectMapper.writeValueAsString(parsed);

        assertThat(parsed.getPrescriptionVerification()).isNotNull();
        assertThat(roundTripped).contains("\"prescriptionVerification\"");
        assertThat(roundTripped).contains("\"target\":\"prescription[1]\"");
        assertThat(roundTripped).contains("\"id\":\"code_in_candidates\"");
        assertThat(roundTripped).contains("Z99");
        // 두 검증이 서로 다른 값을 유지해야 한다 — 병합/혼선이 없어야 한다.
        assertThat(roundTripped).contains("\"id\":\"trace_step_has_observation\"");
        assertThat(roundTripped).contains("\"target\":\"response\"");
    }

    @Test
    void missingPrescriptionVerificationIsNull() throws Exception {
        ValidationAgentResponse parsed = objectMapper.readValue(
                "{\"overallStatus\":\"PASS\",\"summary\":\"s\"}", ValidationAgentResponse.class);

        assertThat(parsed.getPrescriptionVerification()).isNull();
    }
}
