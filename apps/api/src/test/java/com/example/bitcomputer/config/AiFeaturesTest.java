package com.example.bitcomputer.config;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * DR 구성에서 AI 엔드포인트가 무엇을 답하는지 고정한다.
 *
 * <p><b>왜 단위 테스트인가.</b> 이 계약을 통합으로 확인하려면 CSRF 를 포함한
 * 로그인을 먼저 통과해야 한다. 인증에 막히면 503 대신 403 이 나오고, 그러면
 * 그 검사는 "AI 가 꺼졌다" 가 아니라 "인증이 걸렸다" 를 확인하게 된다.
 * 실제로 CI 스크립트를 그렇게 짰다가 403 을 받았다.
 *
 * <p>그래서 역할을 나눈다 — 503 이라는 <b>계약</b>은 여기서 고정하고,
 * CI 의 dr 잡은 <b>스택이 뜨는지</b>에 집중한다. 인증 흐름을 흉내 내는 셸
 * 스크립트는 계약이 바뀌지 않아도 인증이 바뀌면 깨진다.
 */
class AiFeaturesTest {

    @Test
    @DisplayName("AI 가 켜져 있으면 통과시킨다")
    void enabledPassesThrough() {
        assertThatCode(() -> AiFeatures.forTest(true).requireEnabled())
                .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("AI 가 꺼져 있으면 503 을 던진다")
    void disabledThrows503() {
        assertThatThrownBy(() -> AiFeatures.forTest(false).requireEnabled())
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(thrown -> {
                    ResponseStatusException e = (ResponseStatusException) thrown;
                    // 404 가 아니어야 하는 이유: "이 배포에 그 기능이 없다" 와
                    // "주소를 잘못 불렀다" 가 구별되지 않는다.
                    // 500 이 아니어야 하는 이유: 축소 구성은 장애가 아니다.
                    assertThat(e.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
                    assertThat(e.getReason())
                            .as("호출자가 왜 막혔는지 알 수 있어야 한다")
                            .contains("AI");
                });
    }

    /**
     * AI 를 쓰는 서비스가 실제로 가드를 부르는지 본다.
     *
     * <p>{@code requireEnabled()} 가 아무리 정확해도 아무도 부르지 않으면
     * DR 에서 그 코드는 서비스 안쪽까지 들어가 빈이 없어 NPE 를 내고, 그건
     * 500 이 되어 장애처럼 보인다.
     *
     * <p>소스를 읽어 확인한다 — 이 서비스들은 생성자 의존이 많아 단위 테스트로
     * 인스턴스를 만들려면 목을 열 개씩 세워야 하고, 그 목들이 실제 배선과
     * 어긋나면 테스트가 통과해도 아무것도 증명하지 못한다.
     */
    @Test
    @DisplayName("AI 서비스 셋이 모두 가드를 부른다")
    void everyAiServiceCallsTheGuard() throws IOException {
        Path root = repoRoot().resolve("apps/api/src/main/java/com/example/bitcomputer/serviceImpl");
        List<String> mustGuard = List.of(
                "AgentServiceImpl.java",
                "AgentDocumentServiceImpl.java",
                "RadiologyReportServiceImpl.java");

        for (String name : mustGuard) {
            String source = Files.readString(root.resolve(name), StandardCharsets.UTF_8);
            assertThat(source)
                    .as("%s 가 aiFeatures.requireEnabled() 를 부르지 않는다 — "
                            + "DR 구성에서 이 경로는 503 대신 NPE(500)를 낸다", name)
                    .contains("aiFeatures.requireEnabled()");
        }
    }

    /**
     * 기본값이 켜짐인지 본다.
     *
     * <p>이 방향이 반대가 되면 설정 실수 하나로 전체 배포의 AI 가 조용히
     * 사라지고, 화면에서는 DR 구성과 구별되지 않는다. 다른 fail-safe 축들과
     * 방향이 반대인 자리라 명시적으로 고정한다.
     */
    @Test
    @DisplayName("설정이 없으면 AI 는 켜진 것으로 읽는다")
    void defaultsToEnabled() throws IOException {
        Path config = repoRoot().resolve(
                "apps/api/src/main/java/com/example/bitcomputer/config/AiFeatures.java");
        assertThat(Files.readString(config, StandardCharsets.UTF_8))
                .contains("${features.ai.enabled:true}");
    }

    private static Path repoRoot() {
        Path dir = Paths.get("").toAbsolutePath();
        while (dir != null && !Files.exists(dir.resolve("infra/docker-compose.yml"))) {
            dir = dir.getParent();
        }
        if (dir == null) {
            throw new IllegalStateException("저장소 루트를 찾지 못했다");
        }
        return dir;
    }
}
