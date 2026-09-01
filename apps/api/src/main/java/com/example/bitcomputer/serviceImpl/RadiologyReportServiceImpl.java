package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.config.AiFeatures;
import com.example.bitcomputer.Repository.RadiologyReportRepository;
import com.example.bitcomputer.entity.RadiologyReport;
import com.example.bitcomputer.model.RadiologyAnalysisResponseDTO;
import com.example.bitcomputer.model.RadiologyReportRequestDTO;
import com.example.bitcomputer.model.RadiologyReportResponseDTO;
import com.example.bitcomputer.service.RadiologyReportService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

@Slf4j
@Service
public class RadiologyReportServiceImpl implements RadiologyReportService {

    private final RadiologyReportRepository radiologyReportRepository;
    private final RestTemplate restTemplate;
    private final XrayGraphRagClient xrayGraphRagClient;
    private final AiFeatures aiFeatures;
    private final ObjectMapper objectMapper;

    @Value("${ai.api.base-url:http://localhost:5000}")
    private String aiApiBaseUrl;

    @Value("${ai.api.radiology-path:/api/ai/radiology_report}")
    private String flaskRadiologyPath;

    @Value("${radiology.engine:xray}")
    private String radiologyEngine;

    public RadiologyReportServiceImpl(
            RadiologyReportRepository radiologyReportRepository,
            RestTemplate restTemplate,
            XrayGraphRagClient xrayGraphRagClient,
            ObjectMapper objectMapper,
            AiFeatures aiFeatures) {
        this.radiologyReportRepository = radiologyReportRepository;
        this.restTemplate = restTemplate;
        this.xrayGraphRagClient = xrayGraphRagClient;
        this.objectMapper = objectMapper;
        this.aiFeatures = aiFeatures;
    }

    @Override
    public RadiologyAnalysisResponseDTO processRadiologyReport(RadiologyReportRequestDTO request) {
        try {
            AnalysisResult analysisResult = callConfiguredEngine(request);
            RadiologyAnalysisResponseDTO responseDTO = analysisResult.response();
            RadiologyReport report = findOrCreateReport(request);

            report.setResult(analysisResult.positive());
            report.setSummary(serializePredictedDiseases(responseDTO.getPredictedDiseases()));
            report.setImageUrl(responseDTO.getHeatmapUrl());
            report.setStatus("completed");

            if (request.getRadiologyRequestId() == 0) {
                applyRequestFields(report, request);
            }

            radiologyReportRepository.save(report);
            return responseDTO;

        } catch (org.springframework.web.client.HttpClientErrorException e) {
            // HTTP 4xx 오류 (클라이언트 오류)
            String errorBody = e.getResponseBodyAsString();
            log.error("영상판독 API 클라이언트 오류 (HTTP {}): {}", e.getStatusCode(), errorBody, e);
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "AI API에서 오류가 발생했습니다 (HTTP " + e.getStatusCode() + "): " +
                    (errorBody != null && !errorBody.isEmpty() ? errorBody : e.getMessage())
            );
        } catch (org.springframework.web.client.HttpServerErrorException e) {
            // HTTP 5xx 오류 (서버 오류)
            String errorBody = e.getResponseBodyAsString();
            log.error("영상판독 API 서버 오류 (HTTP {}): {}", e.getStatusCode(), errorBody, e);
            
            // JSON 응답에서 error 필드 추출 시도
            String errorMessage = "AI API 서버 오류";
            if (errorBody != null && !errorBody.isEmpty()) {
                try {
                    // 간단한 JSON 파싱 (error 필드 추출)
                    if (errorBody.contains("\"error\"")) {
                        int errorStart = errorBody.indexOf("\"error\"") + 8;
                        int errorEnd = errorBody.indexOf("\"", errorStart);
                        if (errorEnd > errorStart) {
                            errorMessage = errorBody.substring(errorStart, errorEnd);
                        } else {
                            errorMessage = errorBody;
                        }
                    } else {
                        errorMessage = errorBody;
                    }
                } catch (Exception parseEx) {
                    errorMessage = errorBody;
                }
            }
            
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "AI API 서버 오류 (HTTP " + e.getStatusCode() + "): " + errorMessage
            );
        } catch (org.springframework.web.client.ResourceAccessException e) {
            log.error("영상판독 API 서버 연결 실패: {}", e.getMessage(), e);
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "AI API 서버에 연결할 수 없습니다. 영상판독 서버가 실행 중인지 확인하세요: " + e.getMessage()
            );
        } catch (org.springframework.web.client.RestClientException e) {
            log.error("영상판독 API 통신 오류: {}", e.getMessage(), e);
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "AI API와 통신 중 오류가 발생했습니다: " + e.getMessage()
            );
        } catch (ResponseStatusException e) {
            // 상태 코드를 이미 정한 예외는 그대로 올려보낸다.
            //
            // **이것이 없으면 아래 generic catch 가 잡아 전부 500 으로 만든다.**
            // ResponseStatusException 도 RuntimeException 이라 걸린다. 특히
            // AiFeatures.requireEnabled() 의 503 이 그렇게 500 으로 바뀌었다 —
            // 문구는 문자열 안에 남아 살아남지만 상태 코드는 죽는다.
            //
            // 500 은 "고장" 이고 503 은 "이 배포에 그 기능이 없다" 다. AiFeatures 가
            // 404 대신 503 을 고른 이유가 그 구분인데, 여기서 뒤집히면 DR 구성이
            // 장애와 구별되지 않는다. 컨트롤러에 ResponseStatusException 분기가
            // 있는데도 이 catch 앞에서 삼켜져 닿지 못했다.
            throw e;
        } catch (Exception e) {
            log.error("영상 판독 처리 중 예상치 못한 오류 발생: {}", e.getMessage(), e);
            String errorMsg = "영상 판독 처리 중 오류가 발생했습니다: " + e.getMessage();
            if (e.getCause() != null) {
                errorMsg += " (" + e.getCause().getMessage() + ")";
            }
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    errorMsg
            );
        }
    }

    @Override
    public int createRadiologyReportRequest(RadiologyReportRequestDTO request) {
        // 영상판독 요청을 DB에 저장하여 radiologyRequestId 생성
        RadiologyReport report = new RadiologyReport();
        report.setPatientId(request.getPatientId());
        report.setEmployeeId(request.getEmployeeId());
        report.setDeptId(request.getDeptId());
        report.setSymptomDetail(request.getSymptomDetail());
        report.setMemo(request.getMemo());
        report.setEntryDate(request.getEntryDate());
        report.setDetailImageAddress(request.getDetailImageAddress()); // 임시 경로
        report.setResult(null);
        report.setSummary(null);
        report.setImageUrl(null);
        report.setStatus("pending"); // 초기 상태
        
        RadiologyReport savedReport = radiologyReportRepository.save(report);
        log.info("영상판독 요청 생성됨 - radiologyRequestId: {}", savedReport.getRadiologyRequestId());
        
        return savedReport.getRadiologyRequestId();
    }

    private AnalysisResult callConfiguredEngine(RadiologyReportRequestDTO request) {
        // DR 구성에는 xraygraph 도 flask-radiology 도 없다.
        //
        // **이 자리만으로는 부족하다.** 예전 주석은 여기가 "진입점" 이라 pending 이
        // 남지 않는다고 적혀 있었는데, upload-and-analyze 는 이 메서드에 오기 전에
        // 이미 판독 요청을 저장하고 이미지를 쓴다. 그래서 그 컨트롤러는 자기 첫
        // 줄에서 따로 끊는다(RadiologyReportController.uploadAndAnalyze).
        //
        // 여기는 앞선 쓰기가 없는 다른 진입점(POST /report)을 위해 남긴다.
        aiFeatures.requireEnabled();
        if ("flask".equalsIgnoreCase(radiologyEngine)) {
            return callFlaskRadiology(request);
        }
        Path imagePath = resolveImagePath(request.getDetailImageAddress());
        RadiologyAnalysisResponseDTO response = xrayGraphRagClient.infer(imagePath, request.getView());
        boolean positive = response.getPredictedDiseases() != null && !response.getPredictedDiseases().isEmpty();
        return new AnalysisResult(response, positive);
    }

    private AnalysisResult callFlaskRadiology(RadiologyReportRequestDTO request) {
        String url = aiApiBaseUrl + flaskRadiologyPath;
        log.info("Flask 영상판독 API 호출 시작 - URL: {}, 이미지 경로: {}", url, request.getDetailImageAddress());

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<RadiologyReportRequestDTO> httpEntity = new HttpEntity<>(request, headers);

        ResponseEntity<RadiologyReportResponseDTO> response = restTemplate.exchange(
                url, HttpMethod.POST, httpEntity, RadiologyReportResponseDTO.class);

        if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "Flask 영상판독 API에서 응답을 받지 못했습니다.");
        }

        RadiologyReportResponseDTO flask = response.getBody();
        RadiologyAnalysisResponseDTO out = new RadiologyAnalysisResponseDTO();
        out.setHeatmapUrl(flask.getImageUrl());
        out.setPredictedDiseases(new ArrayList<>());
        out.setWarning("기존 Flask 영상판독 엔진은 이상 유무와 heatmap만 제공합니다.");
        // engineStatus / uncertainty 는 일부러 비워 둔다. 이 엔진은 그 두 축을
        // 계산하지 않으므로 여기서 값을 만들면 없는 근거를 지어내는 것이 된다
        // (GC-2). null 은 웹에서 "미확인"으로 렌더된다(GC-3).
        return new AnalysisResult(out, flask.isResult());
    }

    private RadiologyReport findOrCreateReport(RadiologyReportRequestDTO request) {
        if (request.getRadiologyRequestId() > 0) {
            return radiologyReportRepository.findById(request.getRadiologyRequestId())
                    .orElseThrow(() -> new ResponseStatusException(
                            HttpStatus.NOT_FOUND,
                            "영상판독 요청을 찾을 수 없습니다: " + request.getRadiologyRequestId()
                    ));
        }
        RadiologyReport report = new RadiologyReport();
        applyRequestFields(report, request);
        return report;
    }

    private void applyRequestFields(RadiologyReport report, RadiologyReportRequestDTO request) {
        report.setPatientId(request.getPatientId());
        report.setEmployeeId(request.getEmployeeId());
        report.setDeptId(request.getDeptId());
        report.setSymptomDetail(request.getSymptomDetail());
        report.setMemo(request.getMemo());
        report.setEntryDate(request.getEntryDate());
        report.setDetailImageAddress(request.getDetailImageAddress());
    }

    private String serializePredictedDiseases(List<RadiologyAnalysisResponseDTO.PredictedDisease> predictedDiseases) {
        try {
            return objectMapper.writeValueAsString(predictedDiseases != null ? predictedDiseases : List.of());
        } catch (JsonProcessingException e) {
            log.warn("영상판독 predictedDiseases 직렬화 실패", e);
            return "[]";
        }
    }

    private Path resolveImagePath(String imageAddress) {
        if (imageAddress == null || imageAddress.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "이미지 경로가 없습니다.");
        }

        Path raw = Paths.get(imageAddress);
        if (raw.isAbsolute() && Files.exists(raw)) {
            return raw;
        }

        Path cwd = Paths.get("").toAbsolutePath();
        List<Path> candidates = new ArrayList<>();
        candidates.add(cwd.resolve(imageAddress));
        candidates.add(cwd.resolve("BitComputer").resolve(imageAddress));
        if (cwd.getParent() != null) {
            candidates.add(cwd.getParent().resolve("BitComputer").resolve(imageAddress));
        }

        for (Path candidate : candidates) {
            if (Files.exists(candidate)) {
                return candidate;
            }
        }
        throw new ResponseStatusException(HttpStatus.NOT_FOUND, "이미지 파일을 찾을 수 없습니다: " + imageAddress);
    }

    private record AnalysisResult(RadiologyAnalysisResponseDTO response, boolean positive) {
    }
    
    @Override
    public void updateImagePath(int radiologyRequestId, String imagePath) {
        // 영상판독 요청의 이미지 경로 업데이트
        RadiologyReport report = radiologyReportRepository.findById(radiologyRequestId)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "영상판독 요청을 찾을 수 없습니다: " + radiologyRequestId
                ));
        
        report.setDetailImageAddress(imagePath);
        radiologyReportRepository.save(report);
        log.info("이미지 경로 업데이트됨 - radiologyRequestId: {}, imagePath: {}", radiologyRequestId, imagePath);
    }

}
