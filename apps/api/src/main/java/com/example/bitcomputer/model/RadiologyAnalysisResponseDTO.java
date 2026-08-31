package com.example.bitcomputer.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.ArrayList;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class RadiologyAnalysisResponseDTO {
    private String heatmapUrl;
    private List<PredictedDisease> predictedDiseases = new ArrayList<>();
    private String warning;

    /**
     * xray-rag 가 실제 모델로 추론했는지(services/xray-rag 의
     * {@code InferenceResponse.engineStatus}). 설정이 아니라 실행 경로에서
     * 나온다.
     *
     * <p>기본값을 두지 않는다 — 상류가 안 주면 null 이고, 웹은 null 을
     * "real 이 아님"으로 읽어 경고를 띄운다(GC-3 fail-closed). 여기에
     * {@code "real"} 같은 기본값을 넣으면 AIReport 의 엔진 경고가 다시
     * 발화할 수 없는 문구가 된다.
     */
    private String engineStatus;

    /**
     * xray-rag 자신이 계산한 확신도와 그 사유
     * (services/xray-rag 의 {@code InferenceResponse.uncertainty}).
     *
     * <p>{@code level} 만 넘기고 {@code reasons} 를 잃으면 "확신 없음"의 이유가
     * 사라져 의사가 판단할 근거가 없어진다 — 그래서 리스트까지 그대로 옮긴다.
     */
    private Uncertainty uncertainty;

    /**
     * 어느 ROI 분할기가 실제로 구성됐는지: {@code pspnet} / {@code cv} /
     * {@code mock} (services/xray-rag 의 {@code InferenceResponse.roiStatus}).
     *
     * <p>{@code engineStatus} 와 일부러 분리된 축이다. 검색의 기본 경로는 ROI
     * 마스크를 쓰지 않으므로, ROI 가 mock 으로 내려가도 추론 엔진 자체는 real 일
     * 수 있다. 둘을 한 값에 섞으면 어느 쪽이 내려간 것인지 알 수 없어진다.
     *
     * <p>여기서도 기본값을 두지 않는다. 상류가 안 주면 null 이고, 웹은 null 을
     * "모른다"로 읽는다 — {@code "cv"} 같은 기본값을 넣으면 분할기가 고정
     * 타원(mock)까지 떨어진 경우를 정상으로 보고하게 된다(GC-3 fail-closed).
     */
    private String roiStatus;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class Uncertainty {
        /** low | medium | high. 계약 밖 값이나 null 은 웹에서 "미확인"으로 읽힌다. */
        private String level;
        private List<String> reasons = new ArrayList<>();
    }

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class PredictedDisease {
        private String disease;
        private double score;
        private String reason;
    }
}
