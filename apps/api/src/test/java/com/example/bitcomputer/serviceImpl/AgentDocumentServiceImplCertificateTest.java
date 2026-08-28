package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.Repository.EmployeeRepository;
import com.example.bitcomputer.Repository.HistoryDiagnoseRepository;
import com.example.bitcomputer.Repository.HistoryDiseaseRepository;
import com.example.bitcomputer.Repository.HistoryRepository;
import com.example.bitcomputer.Repository.PatientRepository;
import com.example.bitcomputer.entity.History;
import com.example.bitcomputer.entity.Patient;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import com.example.bitcomputer.model.CertificateAgentResponse;
import com.example.bitcomputer.model.GenerateCertificateResponseDTO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Collections;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * {@link AgentDocumentServiceImpl#generateCertificate} 와
 * {@link AgentDocumentServiceImpl#generateTestCertificate} 의 배선을 검증한다.
 *
 * <p>Task 11 리뷰에서 지적된 대로 이 클래스는 스프링 컨텍스트 없이도 생성자
 * 주입만으로 세울 수 있는 평범한 클래스다. {@code resolveCertificateLlmStatus} 는
 * 순수 함수로서 별도 테스트({@link CertificateLlmStatusTest})가 있지만, 그것만으로는
 * 이 메서드가 실제로 호출되는지, 호출 지점에 넘기는 인자가 맞는지 아무것도
 * 보장하지 못한다. 여기서는 {@link CertificateAgentClient} 를 대역으로 세워
 * 실제 흐름(호출 → 필터 → 판정 → 응답 조립)을 끝까지 검증한다.
 */
class AgentDocumentServiceImplCertificateTest {

    private static final int HISTORY_ID = 42;

    private HistoryRepository historyRepository;
    private PatientRepository patientRepository;
    private EmployeeRepository employeeRepository;
    private HistoryDiseaseRepository historyDiseaseRepository;
    private HistoryDiagnoseRepository historyDiagnoseRepository;
    private JwtTokenProvider jwtTokenProvider;
    private CertificateAgentClient certificateAgentClient;

    private AgentDocumentServiceImpl newServiceForGenerateCertificate() {
        historyRepository = mock(HistoryRepository.class);
        patientRepository = mock(PatientRepository.class);
        employeeRepository = mock(EmployeeRepository.class);
        historyDiseaseRepository = mock(HistoryDiseaseRepository.class);
        historyDiagnoseRepository = mock(HistoryDiagnoseRepository.class);
        jwtTokenProvider = mock(JwtTokenProvider.class);
        certificateAgentClient = mock(CertificateAgentClient.class);

        History history = new History();
        history.setId(HISTORY_ID);
        history.setPatientId(1);
        history.setEmployeeId(1);
        history.setDeptId(1);
        history.setEntryDate(LocalDateTime.now());
        history.setSymptomDetail("기침, 발열");

        Patient patient = new Patient();
        patient.setId(1);
        patient.setName("홍길동");
        patient.setBirth(LocalDate.of(1990, 1, 1));
        patient.setGender("M");

        when(historyRepository.findById(HISTORY_ID)).thenReturn(Optional.of(history));
        when(patientRepository.findById(1)).thenReturn(Optional.of(patient));
        when(historyDiseaseRepository.findByHistoryId(HISTORY_ID)).thenReturn(Collections.emptyList());
        when(historyDiagnoseRepository.findByHistoryId(HISTORY_ID)).thenReturn(Collections.emptyList());
        when(employeeRepository.findByUsername(any())).thenReturn(null);
        when(jwtTokenProvider.generateAccessToken(any(), any())).thenReturn("access-token");
        when(jwtTokenProvider.generateRefreshToken(any())).thenReturn("refresh-token");

        return new AgentDocumentServiceImpl(
                historyRepository, patientRepository, employeeRepository, null,
                historyDiseaseRepository, historyDiagnoseRepository, null,
                jwtTokenProvider, certificateAgentClient);
    }

    private AgentDocumentServiceImpl newServiceForGenerateTestCertificate() {
        employeeRepository = mock(EmployeeRepository.class);
        jwtTokenProvider = mock(JwtTokenProvider.class);
        certificateAgentClient = mock(CertificateAgentClient.class);

        when(employeeRepository.findByUsername(any())).thenReturn(null);
        when(jwtTokenProvider.generateAccessToken(any(), any())).thenReturn("access-token");
        when(jwtTokenProvider.generateRefreshToken(any())).thenReturn("refresh-token");

        return new AgentDocumentServiceImpl(
                null, null, employeeRepository, null, null, null, null,
                jwtTokenProvider, certificateAgentClient);
    }

    @Nested
    @DisplayName("generateCertificate")
    class GenerateCertificate {

        @Test
        @DisplayName("에이전트가 실제 소견 텍스트와 real 을 돌려주면 응답도 real")
        void goodTextWithRealStatus_isReal() {
            AgentDocumentServiceImpl service = newServiceForGenerateCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.of(
                    CertificateAgentResponse.builder()
                            .medicalCertificate("환자는 통원 치료가 필요합니다.")
                            .llmStatus("real")
                            .build()));

            GenerateCertificateResponseDTO response =
                    service.generateCertificate(HISTORY_ID, "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getMedicalCertificate()).isEqualTo("환자는 통원 치료가 필요합니다.");
            assertThat(response.getLlmStatus()).isEqualTo("real");
        }

        @Test
        @DisplayName("에이전트가 실제 소견 텍스트와 stub 을 돌려주면 응답도 stub (literal \"real\" 회귀 방지)")
        void goodTextWithStubStatus_isStub() {
            AgentDocumentServiceImpl service = newServiceForGenerateCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.of(
                    CertificateAgentResponse.builder()
                            .medicalCertificate("환자는 통원 치료가 필요합니다.")
                            .llmStatus("stub")
                            .build()));

            GenerateCertificateResponseDTO response =
                    service.generateCertificate(HISTORY_ID, "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getLlmStatus()).isEqualTo("stub");
        }

        @Test
        @DisplayName("에이전트 텍스트가 공백이면 real 이라고 해도 기본 템플릿 + fallback (필터 약화 회귀 방지)")
        void blankTextWithRealStatus_fallsBackToTemplate() {
            AgentDocumentServiceImpl service = newServiceForGenerateCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.of(
                    CertificateAgentResponse.builder()
                            .medicalCertificate("   ")
                            .llmStatus("real")
                            .build()));

            GenerateCertificateResponseDTO response =
                    service.generateCertificate(HISTORY_ID, "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getLlmStatus()).isEqualTo("fallback");
            assertThat(response.getMedicalCertificate()).isNotBlank();
            assertThat(response.getMedicalCertificate()).isNotEqualTo("   ");
            assertThat(response.getMedicalCertificate())
                    .contains("보존적 치료와 증상 조절을 위한 약물치료를 시행하였습니다.");
        }

        @Test
        @DisplayName("에이전트 호출 자체가 실패하면(Optional.empty) 기본 템플릿 + fallback")
        void agentCallFails_fallsBackToTemplate() {
            AgentDocumentServiceImpl service = newServiceForGenerateCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.empty());

            GenerateCertificateResponseDTO response =
                    service.generateCertificate(HISTORY_ID, "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getLlmStatus()).isEqualTo("fallback");
            assertThat(response.getMedicalCertificate())
                    .contains("보존적 치료와 증상 조절을 위한 약물치료를 시행하였습니다.");
        }
    }

    @Nested
    @DisplayName("generateTestCertificate")
    class GenerateTestCertificate {

        @Test
        @DisplayName("에이전트가 실제 소견 텍스트와 real 을 돌려주면 응답도 real")
        void goodTextWithRealStatus_isReal() {
            AgentDocumentServiceImpl service = newServiceForGenerateTestCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.of(
                    CertificateAgentResponse.builder()
                            .medicalCertificate("환자는 통원 치료가 필요합니다.")
                            .llmStatus("real")
                            .build()));

            GenerateCertificateResponseDTO response = service.generateTestCertificate(
                    "J00", "P001", "감기약", "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getMedicalCertificate()).isEqualTo("환자는 통원 치료가 필요합니다.");
            assertThat(response.getLlmStatus()).isEqualTo("real");
        }

        @Test
        @DisplayName("에이전트가 실제 소견 텍스트와 stub 을 돌려주면 응답도 stub (literal \"real\" 회귀 방지)")
        void goodTextWithStubStatus_isStub() {
            AgentDocumentServiceImpl service = newServiceForGenerateTestCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.of(
                    CertificateAgentResponse.builder()
                            .medicalCertificate("환자는 통원 치료가 필요합니다.")
                            .llmStatus("stub")
                            .build()));

            GenerateCertificateResponseDTO response = service.generateTestCertificate(
                    "J00", "P001", "감기약", "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getLlmStatus()).isEqualTo("stub");
        }

        @Test
        @DisplayName("에이전트 텍스트가 공백이면 real 이라고 해도 기본 템플릿 + fallback (필터 약화 회귀 방지)")
        void blankTextWithRealStatus_fallsBackToTemplate() {
            AgentDocumentServiceImpl service = newServiceForGenerateTestCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.of(
                    CertificateAgentResponse.builder()
                            .medicalCertificate("")
                            .llmStatus("real")
                            .build()));

            GenerateCertificateResponseDTO response = service.generateTestCertificate(
                    "J00", "P001", "감기약", "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getLlmStatus()).isEqualTo("fallback");
            assertThat(response.getMedicalCertificate()).isNotBlank();
            assertThat(response.getMedicalCertificate())
                    .contains("보존적 치료와 증상 조절을 위한 약물치료를 시행하였습니다.");
        }

        @Test
        @DisplayName("에이전트 호출 자체가 실패하면(Optional.empty) 기본 템플릿 + fallback")
        void agentCallFails_fallsBackToTemplate() {
            AgentDocumentServiceImpl service = newServiceForGenerateTestCertificate();
            when(certificateAgentClient.generate(any())).thenReturn(Optional.empty());

            GenerateCertificateResponseDTO response = service.generateTestCertificate(
                    "J00", "P001", "감기약", "GENERAL", "FINAL", "제출용", "doctor1");

            assertThat(response.getLlmStatus()).isEqualTo("fallback");
            assertThat(response.getMedicalCertificate())
                    .contains("보존적 치료와 증상 조절을 위한 약물치료를 시행하였습니다.");
        }
    }
}
