package com.example.bitcomputer.serviceImpl;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

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

    /**
     * M12: 오늘의 웹 소비자는 {@code === "real"} 정확 일치만 보므로 "REAL"/"banana"
     * 같은 계약 밖 값도 결과적으로는 fail-closed 지만, 그 사실이 로그 한 줄 없이
     * 지나가면 상류(certificate_api) 계약 위반을 아무도 알아채지 못한다(GC-2).
     */
    @Nested
    class OffContractValues {
        private ListAppender<ILoggingEvent> logAppender;
        private Logger logger;

        @BeforeEach
        void setUpLogCapture() {
            logger = (Logger) LoggerFactory.getLogger(AgentDocumentServiceImpl.class);
            logAppender = new ListAppender<>();
            logAppender.start();
            logger.addAppender(logAppender);
        }

        @AfterEach
        void tearDownLogCapture() {
            logger.detachAppender(logAppender);
        }

        @Test
        void logsWarningForUppercaseOffContractValue() {
            String result = AgentDocumentServiceImpl.resolveCertificateLlmStatus("REAL", true);

            assertThat(result).isEqualTo("REAL");
            assertThat(logAppender.list).hasSize(1);
            ILoggingEvent event = logAppender.list.get(0);
            assertThat(event.getLevel().toString()).isEqualTo("WARN");
            assertThat(event.getFormattedMessage()).contains("REAL");
        }

        @Test
        void logsWarningForUnknownOffContractValue() {
            String result = AgentDocumentServiceImpl.resolveCertificateLlmStatus("banana", true);

            assertThat(result).isEqualTo("banana");
            assertThat(logAppender.list).hasSize(1);
            assertThat(logAppender.list.get(0).getLevel().toString()).isEqualTo("WARN");
        }

        @Test
        void doesNotLogForContractValues() {
            AgentDocumentServiceImpl.resolveCertificateLlmStatus("real", true);
            AgentDocumentServiceImpl.resolveCertificateLlmStatus("stub", true);

            assertThat(logAppender.list).isEmpty();
        }
    }
}
