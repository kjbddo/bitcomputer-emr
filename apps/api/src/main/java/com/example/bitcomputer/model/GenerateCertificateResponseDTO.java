package com.example.bitcomputer.model;

import lombok.Data;

@Data
public class GenerateCertificateResponseDTO {
    private String grantType;
    private String accessToken;
    private String refreshToken;
    private String medicalCertificate;
    /** 소견이 실제로 모델에서 나왔는지: "real" | "stub" | "fallback". */
    private String llmStatus;
}
