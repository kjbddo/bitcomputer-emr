package com.example.bitcomputer.serviceImpl;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CertificateLlmStatusTest {

    @Test
    void usesUpstreamStatusWhenAgentTextWasUsed() {
        assertThat(AgentDocumentServiceImpl.resolveCertificateLlmStatus("real", true))
                .isEqualTo("real");
        assertThat(AgentDocumentServiceImpl.resolveCertificateLlmStatus("stub", true))
                .isEqualTo("stub");
    }

    /**
     * 템플릿으로 떨어졌으면 상류가 뭐라고 했든 모델은 이 소견에 관여하지 않았다.
     * 이 분기를 상류 값으로 두면 "real" 라벨이 붙은 템플릿 문장이 나간다.
     */
    @Test
    void reportsFallbackWhenDefaultTemplateWasUsed() {
        assertThat(AgentDocumentServiceImpl.resolveCertificateLlmStatus("real", false))
                .isEqualTo("fallback");
    }

    @Test
    void missingUpstreamStatusFailsClosed() {
        assertThat(AgentDocumentServiceImpl.resolveCertificateLlmStatus(null, true))
                .isEqualTo("fallback");
        assertThat(AgentDocumentServiceImpl.resolveCertificateLlmStatus("  ", true))
                .isEqualTo("fallback");
    }
}
