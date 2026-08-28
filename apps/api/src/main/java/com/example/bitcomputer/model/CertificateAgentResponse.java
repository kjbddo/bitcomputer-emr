package com.example.bitcomputer.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Python(FastAPI) certificate_api → Spring 응답 본문.
 *
 * <p>LLM 게이트웨이(services/llm-gateway) 경유로 생성된 진단서 소견 문자열이
 * {@code medicalCertificate} 에 담긴다.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class CertificateAgentResponse {

    /** LLM 게이트웨이 경유로 생성된 진단서 소견 문자열. */
    @JsonProperty("medicalCertificate")
    private String medicalCertificate;

    /**
     * 이 응답이 실제로 모델에서 나왔는지. 설정이 아니라 실행 경로에서 나온다.
     *
     * <p>상류가 이 필드를 안 주면 "모델 미사용" 쪽으로만 틀린다. 누락을 조용히
     * "모델이 돌았다"로 읽으면 이 필드가 존재할 이유가 사라진다.
     */
    @Builder.Default
    @JsonProperty("llmStatus")
    private String llmStatus = "fallback";
}
