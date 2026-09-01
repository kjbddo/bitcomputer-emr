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
     * 가드가 던진 503 이 끝까지 503 으로 나가는지 본다.
     *
     * <p>{@code processRadiologyReport} 의 마지막 {@code catch (Exception e)} 는
     * {@code ResponseStatusException} 도 잡는다 — 그것도 RuntimeException 이다.
     * 그 앞에 다시 던지는 분기가 없으면 가드의 503 이 500 으로 바뀐다. 문구는
     * 문자열 안에 남아 살아남으므로 <b>화면에는 그럴듯한 안내가 뜨는데 상태 코드만
     * 틀린 상태</b>가 되고, 그건 눈으로 보고 알아채기 어렵다.
     *
     * <p>500 은 "고장" 이고 503 은 "이 배포에 그 기능이 없다" 다. 그 구분을 지키려고
     * 404 대신 503 을 골랐으므로, 여기서 뒤집히면 그 선택이 무의미해진다.
     */
    @Test
    @DisplayName("영상판독은 상태 코드가 정해진 예외를 그대로 올려보낸다")
    void radiologyRethrowsResponseStatusException() throws IOException {
        Path impl = repoRoot().resolve(
                "apps/api/src/main/java/com/example/bitcomputer/serviceImpl/RadiologyReportServiceImpl.java");
        String source = Files.readString(impl, StandardCharsets.UTF_8);

        int rethrow = source.indexOf("catch (ResponseStatusException e)");
        int generic = source.indexOf("catch (Exception e)");

        assertThat(rethrow)
                .as("ResponseStatusException 을 다시 던지는 분기가 없다 — 가드의 503 이 500 이 된다")
                .isNotEqualTo(-1);
        assertThat(rethrow)
                .as("그 분기가 generic catch 뒤에 있으면 도달하지 못한다")
                .isLessThan(generic);
    }

    /**
     * 업로드 경로가 <b>아무것도 쓰기 전에</b> 가드를 부르는지 본다.
     *
     * <p>{@code uploadAndAnalyze} 는 판독 요청을 DB 에 저장하고 업로드 이미지를
     * 디스크에 쓴 <i>다음</i> 엔진을 부른다. 가드가 엔진 쪽에만 있으면 DR 에서
     * 버튼을 누를 때마다 고아 {@code pending} 레코드와 이미지가 쌓인다 — 사용자는
     * 503 을 받으니 아무 일도 없었다고 생각하는데 저장소에는 남는다.
     *
     * <p>순서로 고정한다. 가드를 호출하기만 하고 위치가 뒤로 밀리면 이 검사가
     * 걸린다.
     */
    @Test
    @DisplayName("업로드 경로는 저장보다 먼저 가드를 부른다")
    void uploadGuardsBeforeAnyWrite() throws IOException {
        Path controller = repoRoot().resolve(
                "apps/api/src/main/java/com/example/bitcomputer/controller/RadiologyReportController.java");
        String source = Files.readString(controller, StandardCharsets.UTF_8);

        int guard = source.indexOf("aiFeatures.requireEnabled()");
        int dbWrite = source.indexOf("createRadiologyReportRequest(");
        int fileWrite = source.indexOf("imageStorageUtil.saveImage(");

        assertThat(guard).as("컨트롤러가 가드를 부르지 않는다").isNotEqualTo(-1);
        assertThat(dbWrite).isNotEqualTo(-1);
        assertThat(fileWrite).isNotEqualTo(-1);
        assertThat(guard)
                .as("가드보다 DB 저장이 먼저다 — DR 에 고아 pending 레코드가 남는다")
                .isLessThan(dbWrite);
        assertThat(guard)
                .as("가드보다 이미지 저장이 먼저다 — DR 에 업로드 파일이 남는다")
                .isLessThan(fileWrite);
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
