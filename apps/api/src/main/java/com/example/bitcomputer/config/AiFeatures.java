package com.example.bitcomputer.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import jakarta.annotation.PostConstruct;

/**
 * 이 배포에 AI 기능이 있는지.
 *
 * <p><b>왜 있는가.</b> DR(재해 복구) 시나리오는 AI 없이 3-tier 만 새로 세우는
 * 것이다. 진료 기록을 읽고 쓰는 것은 병원이 멈추면 안 되는 일이고, 처방 추천과
 * X-ray 분석은 그렇지 않다. 후자를 빼면 복구해야 할 것이 프론트·API·DB 셋으로
 * 줄고, 이미지 총량도 14.4GB 에서 4.5GB 가 된다.
 *
 * <p>이 플래그가 꺼지면 다음이 함께 꺼진다:
 * <ul>
 *   <li>RabbitMQ 배선({@code ValidationRabbitConfig}, {@code ValidationJobResultConsumer})
 *       — 검증 job 큐는 AI 전용이다</li>
 *   <li>ArangoDB 배선({@code ArangoConfig}) — 처방 그래프와 X-ray 그래프 전용이다.
 *       참고로 Spring 쪽 Arango 리포지토리는 **AI 를 켜 둔 지금도 아무도 쓰지
 *       않는다.** 그래프는 prescription-api 가 직접 붙는다</li>
 *   <li>AI 엔드포인트 — 503 을 낸다</li>
 * </ul>
 *
 * <p><b>왜 라우팅에서 빼지 않고 503 을 내는가.</b> 없는 경로로 두면 404 가
 * 나가는데, 그건 "이 배포에는 그 기능이 없다" 와 "주소를 잘못 불렀다" 를
 * 구별하지 못한다. 503 + 명시적 문구는 호출자가 무엇이 벌어졌는지 바로 안다.
 * 프론트가 실수로 호출해도 연결 타임아웃을 기다리지 않고 즉시 답을 받는다.
 */
@Slf4j
@Component
public class AiFeatures {

    /**
     * 기본값은 true 다.
     *
     * <p>fail-safe 방향을 여기서만 반대로 잡는다. 이 값이 없을 때 false 로
     * 떨어지면 설정 실수 하나로 전체 배포의 AI 가 조용히 사라지고, 화면에서는
     * "DR 모드" 와 구별되지 않는다. AI 를 끄는 것은 명시적 선택이어야 한다.
     */
    @Value("${features.ai.enabled:true}")
    private boolean enabled;

    @PostConstruct
    void announce() {
        if (!enabled) {
            log.warn("AI 기능이 꺼진 상태로 기동합니다(features.ai.enabled=false). "
                    + "처방 추천·진단서 생성·X-ray 분석 엔드포인트는 503 을 냅니다. "
                    + "RabbitMQ / ArangoDB 배선도 함께 비활성화됩니다.");
        }
    }

    /**
     * 테스트용 인스턴스. Spring 컨텍스트 없이 이 값을 고정한다.
     *
     * <p>단위 테스트는 서비스를 직접 생성자로 만든다. 그때 이 클래스를 실제
     * 빈으로 받을 수 없으므로 여기서 만들어 준다. 테스트가 각자 목을 만들면
     * {@code requireEnabled()} 의 실제 동작(503 을 던진다)이 테스트마다 달라져,
     * 정작 그 동작을 아무도 검증하지 않게 된다.
     */
    public static AiFeatures forTest(boolean enabled) {
        AiFeatures features = new AiFeatures();
        features.enabled = enabled;
        return features;
    }

    public boolean isEnabled() {
        return enabled;
    }

    /**
     * AI 가 꺼져 있으면 503 으로 끊는다.
     *
     * <p>AI 엔드포인트의 첫 줄에서 부른다. 서비스 안쪽까지 들어간 뒤 빈이 없어
     * {@code NullPointerException} 이 나면 500 이 되는데, 그건 장애처럼 보인다 —
     * 이 배포에 그 기능이 없는 것은 장애가 아니다.
     */
    public void requireEnabled() {
        if (!enabled) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "이 배포에는 AI 기능이 포함되어 있지 않습니다(DR 구성). "
                            + "처방 추천·진단서 생성·X-ray 분석은 전체 스택에서만 동작합니다.");
        }
    }
}
