package com.example.bitcomputer.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.time.LocalDateTime;

@Entity
@Table(name = "medical_certificate")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class MedicalCertificateRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(name = "history_id", nullable = false)
    private Integer historyId;

    @Column(name = "pdf_file_path")
    private String pdfFilePath;

    @Column(name = "agent_used", nullable = false)
    private boolean agentUsed;

    /**
     * 이 진단서 소견이 실제로 모델에서 나왔는지: "real" | "stub" | "fallback".
     *
     * <p>{@code agentUsed} 는 "의사가 AI 도움을 요청했나"만 말한다 — 실제로 모델이
     * 문장을 만들었는지는 별개다. 이 필드가 그 질문에 답한다. 값은 설정이 아니라
     * 실행 경로(생성 시점에 파이썬 certificate_api 가 보고한 llmStatus)에서 온다.
     * 근거가 없으면(캐시 미스, AI 미사용 등) {@code null} 이다 — "real" 로 기본값이
     * 새면 미검증 상태가 검증된 것처럼 저장된다(GC-2 와 같은 원칙).
     */
    @Column(name = "llm_status", length = 20)
    private String llmStatus;

    @Column(name = "original_medical_certificate", columnDefinition = "TEXT")
    private String originalMedicalCertificate;

    @Column(name = "saved_medical_certificate", columnDefinition = "TEXT")
    private String savedMedicalCertificate;

    @Column(name = "feedback_type", length = 20)
    private String feedbackType; // APPROVE / MODIFY / REJECT / NONE

    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
