package com.example.bitcomputer.model;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CertificateAgentResponseTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * @JsonIgnoreProperties(ignoreUnknown = true) 가 붙어 있으므로 DTO 가 모르는
     * 필드는 조용히 사라진다. 값까지 단언해야 "필드가 선언돼 있다"가 아니라
     * "상류 값이 살아남았다"를 검증한다.
     */
    @Test
    void parsesLlmStatusFromUpstream() throws Exception {
        String upstream = "{\"medicalCertificate\":\"소견\",\"llmStatus\":\"stub\"}";

        CertificateAgentResponse parsed =
                objectMapper.readValue(upstream, CertificateAgentResponse.class);

        assertThat(parsed.getMedicalCertificate()).isEqualTo("소견");
        assertThat(parsed.getLlmStatus()).isEqualTo("stub");
    }

    /**
     * 상류가 필드를 안 줬을 때 "모델이 돌았다"로 기울면 안 된다.
     * 파이썬 쪽과 같은 방향(fail-closed)으로 맞춘다.
     */
    @Test
    void missingLlmStatusFailsClosed() throws Exception {
        CertificateAgentResponse parsed = objectMapper.readValue(
                "{\"medicalCertificate\":\"소견\"}", CertificateAgentResponse.class);

        assertThat(parsed.getLlmStatus()).isEqualTo("fallback");
    }
}
