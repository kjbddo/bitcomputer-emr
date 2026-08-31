package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.model.RadiologyAnalysisResponseDTO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

/**
 * F-H4: xray-rag 는 이 시스템에서 가장 정직한 산출물을 만든다 —
 * {@code engineStatus} 와 사유가 붙은 {@code uncertainty}. 그 둘이 Spring
 * 경계에서 사라지면 노이즈 이미지에 대해 의사가 보는 것은 병명과 점수뿐이고,
 * AIReport.tsx 의 엔진 경고는 어떤 경로로도 발화할 수 없는 죽은 문구가 된다.
 *
 * <p>이 테스트는 DTO 단위가 아니라 실제 HTTP 경계(XrayGraphRagClient.infer)를
 * 통과시킨다 — 필드를 DTO 에 선언해 놓고 매핑에서 빠뜨리는 것이 이 경로에서
 * 가장 쉬운 실수이기 때문이다.
 */
class XrayGraphRagClientProvenanceTest {

    private RestTemplate restTemplate;
    private MockRestServiceServer server;
    private XrayGraphRagClient client;

    @TempDir
    Path tempDir;

    @BeforeEach
    void setUp() {
        restTemplate = new RestTemplate();
        server = MockRestServiceServer.createServer(restTemplate);
        client = new XrayGraphRagClient(restTemplate);
        ReflectionTestUtils.setField(client, "baseUrl", "http://xray.test:8000");
        ReflectionTestUtils.setField(client, "publicBaseUrl", "http://xray.test:8000");
        ReflectionTestUtils.setField(client, "path", "/infer");
        ReflectionTestUtils.setField(client, "defaultView", "AP");
        ReflectionTestUtils.setField(client, "topK", 5);
    }

    private Path anImage() throws Exception {
        Path image = tempDir.resolve("xray.png");
        Files.write(image, new byte[] {1, 2, 3});
        return image;
    }

    /**
     * 노이즈 PNG 에 대한 실측 응답을 그대로 본뜬 페이로드다(리뷰 F-H4 라이브
     * 근거). 사유 넷이 전부 살아남아야 한다 — level 만 넘기고 reasons 를
     * 잃으면 "확신 없음"의 이유가 사라져 의사가 판단할 근거가 없어진다.
     */
    @Test
    void inferCarriesEngineStatusAndUncertaintyToTheDto() throws Exception {
        String body = "{"
                + "\"predictedDiseases\":[{\"disease\":\"lung_opacity\",\"score\":0.2,"
                + "\"supportCases\":1,\"reason\":\"유사 사례 1건\"}],"
                + "\"notableFindings\":[],\"similarCases\":[],"
                + "\"uncertainty\":{\"level\":\"high\",\"reasons\":["
                + "\"Top-1 similarity(0.63) is below threshold(0.65)\","
                + "\"Average top-k similarity(0.43) is low\","
                + "\"Top-1 disease score and Top-2 disease score are close (gap=0.00)\","
                + "\"Only 5 similar cases found\"]},"
                + "\"explanation\":{\"summary\":\"...\"},"
                + "\"heatmapPath\":\"/storage/h.png\","
                + "\"warning\":\"진단이 아닙니다\","
                + "\"engineStatus\":\"mock\""
                + "}";

        server.expect(requestTo("http://xray.test:8000/infer"))
                .andRespond(withSuccess(body, MediaType.APPLICATION_JSON));

        RadiologyAnalysisResponseDTO out = client.infer(anImage(), "PA");

        server.verify();
        assertThat(out.getEngineStatus()).isEqualTo("mock");
        assertThat(out.getUncertainty()).isNotNull();
        assertThat(out.getUncertainty().getLevel()).isEqualTo("high");
        assertThat(out.getUncertainty().getReasons())
                .hasSize(4)
                .contains("Only 5 similar cases found");
    }

    /**
     * 상류가 두 필드를 안 주면 null 이어야 한다. 여기서 "real" 이나 level="low"
     * 같은 기본값을 만들면 모르는 것을 아는 것처럼 만드는 셈이고, 웹의
     * fail-closed 렌더(GC-3)가 발동할 수 없게 된다.
     */
    @Test
    void missingProvenanceStaysNullInsteadOfClaimingReal() throws Exception {
        String body = "{\"predictedDiseases\":[],\"heatmapPath\":null,\"warning\":\"w\"}";

        server.expect(requestTo("http://xray.test:8000/infer"))
                .andRespond(withSuccess(body, MediaType.APPLICATION_JSON));

        RadiologyAnalysisResponseDTO out = client.infer(anImage(), "PA");

        server.verify();
        assertThat(out.getEngineStatus()).isNull();
        assertThat(out.getUncertainty()).isNull();
    }
}
