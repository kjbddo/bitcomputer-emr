package com.example.bitcomputer.model;

import com.example.bitcomputer.serviceImpl.XrayGraphRagClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.fail;

/**
 * 파이썬 서비스가 만든 provenance 신호가 그것을 중계하는 Java DTO 를 지나
 * 살아남는지 확인하는 경계 회귀 테스트.
 *
 * <p><b>왜 있는가.</b> 이 저장소의 Java DTO 는 모두
 * {@code @JsonIgnoreProperties(ignoreUnknown = true)} 다. 상류가 새 필드를
 * 추가해도 DTO 가 그 필드를 선언하지 않으면 역직렬화에서 조용히 사라지고,
 * 다시 직렬화될 때는 애초에 없었던 것과 구별되지 않는다. 이 구조가 같은 결함을
 * 세 번 만들었다(F-H3 처방 배지, F-H4 xray uncertainty, F-M6 처방 DTO).
 * 컴파일러도 테스트도 아무 말을 하지 않는 종류의 손실이라, 무언가가 직접
 * 확인하지 않으면 계속 반복된다.
 *
 * <p><b>무엇을 하는가.</b> 아래 {@link #BOUNDARIES} 의 각 쌍에 대해
 * <ol>
 *   <li>파이썬 소스에서 응답 모델 클래스의 필드 선언을 직접 파싱하고,</li>
 *   <li>이름이 provenance 어휘({@link #PROVENANCE_TOKENS})에 걸리는 필드만 골라,</li>
 *   <li>그 필드마다 파이썬 타입 주석에서 모양을 유추한 탐침 값을 담은 JSON 을 만들고,</li>
 *   <li>실제 Jackson 으로 Java DTO 에 역직렬화 → 재직렬화한 뒤,</li>
 *   <li>탐침 값이 그 왕복에서 전부 살아남았는지 확인한다.</li>
 * </ol>
 * 즉 "필드 이름이 양쪽에 있다"가 아니라 "값이 경계를 통과한다"를 본다. 결함을
 * 만든 메커니즘 자체(Jackson 왕복)를 그대로 태우는 방식이다.
 *
 * <p><b>무엇을 못 하는가(의도적 한계).</b>
 * <ul>
 *   <li>이름 규칙에 의존한다. provenance 어휘에 걸리지 않는 이름으로 새 신호를
 *       만들면(예: {@code groundedness}) 이 테스트는 그것을 모른다. 새 축을
 *       추가할 때 {@link #PROVENANCE_TOKENS} 에 한 줄 넣는 것이 이 테스트를
 *       유지하는 유일한 수작업이다.</li>
 *   <li>DTO 를 지난 뒤의 일은 보지 않는다. Java 가 필드를 받아 놓고 외부 응답
 *       DTO 로 옮기지 않거나, 웹 타입에 선언하지 않거나, 화면에 그리지 않는
 *       것은 여기서 안 잡힌다. 그 구간은 각 경로의 개별 테스트가 맡는다
 *       (예: XrayGraphRagClientProvenanceTest 는 HTTP 응답에서
 *       RadiologyAnalysisResponseDTO 까지의 매핑을, 웹 테스트는 배지 렌더를).</li>
 *   <li>중첩은 한 단계만 본다. 파이썬 중첩 모델의 필드까지는 탐침을 만들지만
 *       그 안의 또 다른 모델까지는 문자열 탐침으로 떨어진다.</li>
 *   <li>값의 <i>의미</i>는 보지 않는다. "stub" 이 "real" 로 바뀌어 도착해도
 *       살아남기만 하면 통과한다. 그건 각 축의 fail-closed 테스트가 맡는다.</li>
 * </ul>
 */
class PythonProvenanceFieldsSurviveJavaDtoTest {

    /**
     * provenance 어휘. 파이썬 응답 모델의 필드 이름을 소문자로 바꿔 이 조각 중
     * 하나라도 포함하면 "출처/검증 신호"로 보고 경계 통과를 강제한다.
     *
     * <p>{@code explanation} 은 일부러 넣지 않았다 — xray-rag 의
     * {@code explanation} 은 계약 없는 산문 묶음이고, 그 안의 provenance 성
     * 내용({@code uncertainty}, {@code warning})은 이미 최상위 필드로 따로
     * 건너온다. 어휘에 넣으면 같은 신호의 두 번째 사본을 강제하게 된다.
     */
    private static final List<String> PROVENANCE_TOKENS = List.of(
            "llmstatus",
            "enginestatus",
            "roistatus",
            "verification",
            "uncertainty",
            "embeddingversion");

    /** 파이썬 응답 모델 ↔ 그것을 역직렬화하는 Java DTO. */
    private record Boundary(String pythonRelPath, String pythonClass, Class<?> javaDto) {
        @Override
        public String toString() {
            return pythonRelPath + "::" + pythonClass + " -> " + javaDto.getSimpleName();
        }
    }

    /*
     * prescription_api 의 PrescriptionRecommendResponse 는 여기 없다. 그 응답을
     * Java 로 받던 유일한 경로(AgentServiceImpl.callAgentAndMap →
     * PrescriptionAgentClient.recommend)가 죽은 코드라 삭제됐고, 지금 그 응답을
     * 받는 것은 validation-agent(파이썬)다. 그쪽의 출처·검증은
     * ValidationAgentResponse 의 prescriptionLlmStatus / prescriptionVerification
     * 로 건너오므로 이 목록의 첫 번째 경계가 이미 덮는다. 동기 경로를 되살리지
     * 않는 한 다시 넣지 말 것.
     */
    private static final List<Boundary> BOUNDARIES = List.of(
            new Boundary(
                    "services/validation-agent/app/models.py",
                    "ValidationAgentResponse",
                    ValidationAgentResponse.class),
            new Boundary(
                    "services/prescription/certificate_api.py",
                    "CertificateGenerateResponse",
                    CertificateAgentResponse.class),
            new Boundary(
                    "services/xray-rag/app/models/schemas.py",
                    "InferenceResponse",
                    XrayGraphRagClient.XrayInferResponse.class));

    private final ObjectMapper objectMapper = new ObjectMapper();

    @TestFactory
    List<DynamicTest> everyPythonProvenanceFieldSurvivesItsJavaDto() throws IOException {
        Path repoRoot = repoRoot();
        List<DynamicTest> tests = new ArrayList<>();
        for (Boundary boundary : BOUNDARIES) {
            tests.add(DynamicTest.dynamicTest(boundary.toString(), () -> checkBoundary(repoRoot, boundary)));
        }
        return tests;
    }

    private void checkBoundary(Path repoRoot, Boundary boundary) throws Exception {
        Path pythonFile = repoRoot.resolve(boundary.pythonRelPath());
        if (!Files.isRegularFile(pythonFile)) {
            fail("파이썬 응답 모델 파일을 찾을 수 없다: " + pythonFile
                    + " — 파일이 옮겨졌다면 이 테스트의 BOUNDARIES 도 함께 고쳐야 한다.");
        }
        String source = Files.readString(pythonFile, StandardCharsets.UTF_8);

        Map<String, String> fields = pythonClassFields(source, boundary.pythonClass());
        if (fields.isEmpty()) {
            fail("파이썬 클래스 " + boundary.pythonClass() + " 를 " + boundary.pythonRelPath()
                    + " 에서 찾지 못했거나 필드가 하나도 파싱되지 않았다."
                    + " 클래스 이름이 바뀌었다면 BOUNDARIES 를 고쳐야 한다 —"
                    + " 그냥 두면 이 경계는 아무것도 검사하지 않는 상태로 조용히 통과한다.");
        }

        Map<String, String> provenance = new LinkedHashMap<>();
        fields.forEach((name, annotation) -> {
            if (isProvenanceName(name)) {
                provenance.put(name, annotation);
            }
        });
        assertThat(provenance)
                .as("%s 에 provenance 필드가 하나도 없다 — 어휘(PROVENANCE_TOKENS)나"
                        + " 파이썬 모델 중 하나가 바뀌었다는 뜻이다", boundary)
                .isNotEmpty();

        ObjectNode probe = objectMapper.createObjectNode();
        provenance.forEach((name, annotation) ->
                probe.set(name, probeValue(name, annotation, source)));

        Object parsed;
        try {
            parsed = objectMapper.readValue(objectMapper.writeValueAsString(probe), boundary.javaDto());
        } catch (Exception e) {
            // 필드는 선언돼 있는데 Java 쪽 타입이 파이썬 주석과 다른 경우다 —
            // 조용히 버려지는 것과 마찬가지로 값이 경계를 넘지 못한다.
            throw new AssertionError(String.format(Locale.ROOT,
                    "provenance 탐침이 %s 에 역직렬화되지 않았다 — 선언된 타입이 파이썬 주석과 다르다.%n"
                            + "  파이썬: %s::%s%n  보낸 값: %s%n  원인: %s",
                    boundary.javaDto().getName(),
                    boundary.pythonRelPath(), boundary.pythonClass(), probe, e.getMessage()), e);
        }
        JsonNode roundTripped = objectMapper.valueToTree(parsed);

        for (String name : provenance.keySet()) {
            JsonNode expected = probe.get(name);
            JsonNode actual = roundTripped.get(name);
            if (actual == null || actual.isNull() || !containsSubtree(expected, actual)) {
                fail(String.format(Locale.ROOT,
                        "provenance 필드가 경계에서 사라졌다.%n"
                                + "  파이썬: %s::%s.%s%n"
                                + "  Java  : %s%n"
                                + "  보낸 값: %s%n"
                                + "  돌아온 값: %s%n"
                                + "%s 에 이 필드를 선언하면 된다."
                                + " @JsonIgnoreProperties(ignoreUnknown = true) 때문에"
                                + " 선언하지 않은 필드는 예외 없이 조용히 버려진다.",
                        boundary.pythonRelPath(), boundary.pythonClass(), name,
                        boundary.javaDto().getName(),
                        expected, actual,
                        boundary.javaDto().getSimpleName()));
            }
        }
    }

    // ---------------------------------------------------------------- helpers

    private static boolean isProvenanceName(String fieldName) {
        String lowered = fieldName.toLowerCase(Locale.ROOT);
        return PROVENANCE_TOKENS.stream().anyMatch(lowered::contains);
    }

    /**
     * 파이썬 소스에서 한 클래스 본문의 4칸 들여쓰기 필드 선언(`name: annotation`)을
     * 선언 순서대로 뽑는다. 클래스 본문은 다음 최상위(들여쓰기 0) 문장에서 끝난다.
     */
    private static Map<String, String> pythonClassFields(String source, String className) {
        Map<String, String> out = new LinkedHashMap<>();
        Pattern classStart = Pattern.compile("^class\\s+" + Pattern.quote(className) + "\\b.*:\\s*$");
        Pattern field = Pattern.compile("^ {4}([A-Za-z_][A-Za-z0-9_]*)\\s*:\\s*(\\S.*)$");

        boolean inside = false;
        for (String line : source.split("\\R", -1)) {
            if (!inside) {
                if (classStart.matcher(line).matches()) {
                    inside = true;
                }
                continue;
            }
            if (!line.isBlank() && !Character.isWhitespace(line.charAt(0))) {
                break; // 다음 최상위 문장 — 클래스 본문 끝
            }
            Matcher m = field.matcher(line);
            if (m.matches()) {
                out.put(m.group(1), m.group(2).trim());
            }
        }
        return out;
    }

    /**
     * 파이썬 타입 주석에서 탐침 값의 모양을 유추한다. 모양이 안 맞으면
     * 역직렬화가 값을 버리거나 예외를 내므로, "선언은 있는데 타입이 다르다"도
     * 여기서 함께 걸린다.
     */
    private JsonNode probeValue(String fieldName, String annotation, String pythonSource) {
        String marker = "__probe_" + fieldName + "__";
        // 부분 문자열이 아니라 낱말 경계로 본다. `Uncertainty` 안의 "int" 처럼
        // 타입 이름에 우연히 들어 있는 조각을 원시 타입으로 오인하면, 탐침 값의
        // 모양이 틀려서 이 테스트가 실제 결함이 아닌 이유로 빨개진다.
        if (mentionsType(annotation, "Dict")) {
            ObjectNode node = objectMapper.createObjectNode();
            node.put("probe", marker);
            return node;
        }
        if (mentionsType(annotation, "List")) {
            ArrayNode node = objectMapper.createArrayNode();
            node.add(marker);
            return node;
        }
        if (mentionsType(annotation, "bool")) {
            return objectMapper.getNodeFactory().booleanNode(true);
        }
        if (mentionsType(annotation, "int") || mentionsType(annotation, "float")) {
            return objectMapper.getNodeFactory().numberNode(4242);
        }
        String nested = nestedModelName(annotation);
        if (nested != null) {
            Map<String, String> nestedFields = pythonClassFields(pythonSource, nested);
            if (!nestedFields.isEmpty()) {
                ObjectNode node = objectMapper.createObjectNode();
                nestedFields.forEach((name, ann) ->
                        node.set(name, probeValue(fieldName + "_" + name, ann, "")));
                return node;
            }
        }
        return objectMapper.getNodeFactory().textNode(marker);
    }

    private static boolean mentionsType(String annotation, String typeName) {
        return Pattern.compile("\\b" + Pattern.quote(typeName) + "\\b").matcher(annotation).find();
    }

    /** {@code Optional[Uncertainty] = None} 같은 주석에서 모델 이름만 뽑는다. */
    private static String nestedModelName(String annotation) {
        Matcher m = Pattern.compile("([A-Z][A-Za-z0-9_]*)").matcher(annotation);
        while (m.find()) {
            String candidate = m.group(1);
            if (!candidate.equals("Optional") && !candidate.equals("Any")
                    && !candidate.equals("Field") && !candidate.equals("Literal")
                    && !candidate.equals("None")) {
                return candidate;
            }
        }
        return null;
    }

    /** expected 의 모든 잎이 actual 안에 그대로 있는지. Java 가 필드를 더 갖는 것은 허용한다. */
    private static boolean containsSubtree(JsonNode expected, JsonNode actual) {
        if (actual == null || actual.isNull()) {
            return false;
        }
        if (expected.isObject()) {
            if (!actual.isObject()) {
                return false;
            }
            var names = expected.fieldNames();
            while (names.hasNext()) {
                String name = names.next();
                if (!containsSubtree(expected.get(name), actual.get(name))) {
                    return false;
                }
            }
            return true;
        }
        if (expected.isArray()) {
            if (!actual.isArray() || actual.size() < expected.size()) {
                return false;
            }
            for (int i = 0; i < expected.size(); i++) {
                if (!containsSubtree(expected.get(i), actual.get(i))) {
                    return false;
                }
            }
            return true;
        }
        return expected.equals(actual);
    }

    /**
     * 저장소 루트를 찾는다. Gradle 은 apps/api 를 작업 디렉터리로 쓰지만 IDE 나
     * CI 에서 달라질 수 있으므로 위로 올라가며 표지({@code services/} +
     * {@code apps/})를 찾는다. 못 찾으면 skip 하지 않고 실패한다 — 조용히
     * 넘어가면 이 테스트가 아무것도 지키지 않는 상태로 남는다.
     */
    private static Path repoRoot() {
        Path dir = Paths.get("").toAbsolutePath();
        while (dir != null) {
            if (Files.isDirectory(dir.resolve("services")) && Files.isDirectory(dir.resolve("apps"))) {
                return dir;
            }
            dir = dir.getParent();
        }
        throw new IllegalStateException(
                "저장소 루트(services/ 와 apps/ 를 함께 가진 디렉터리)를 찾지 못했다. 작업 디렉터리="
                        + Paths.get("").toAbsolutePath());
    }
}
