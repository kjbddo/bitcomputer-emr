package com.example.bitcomputer.config;

import org.mockito.Mockito;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

@TestConfiguration
public class TestRedisConfig {

    // AppConfig 가 이미 같은 타입의 RedisTemplate 빈을 정의하고 있고, 두 @Configuration
    // 클래스의 처리 순서가 보장되지 않아 같은 빈 이름으로 override 를 노려도 실제 Lettuce
    // 빈이 이길 때가 있었다. 이름을 다르게 두고 @Primary 로 확정적으로 우선시킨다.
    @Bean
    @Primary
    @SuppressWarnings("unchecked")
    public RedisTemplate<String, Object> mockRedisTemplate() {
        RedisTemplate<String, Object> template = Mockito.mock(RedisTemplate.class);
        ValueOperations<String, Object> ops = Mockito.mock(ValueOperations.class);
        Mockito.when(template.opsForValue()).thenReturn(ops);
        Mockito.when(template.hasKey(Mockito.anyString())).thenReturn(false);
        return template;
    }

    // RedisAutoConfiguration 을 제외하면 MainController 가 주입받는
    // StringRedisTemplate 빈도 함께 사라진다. 헬스체크용 목 빈을 별도로 둔다.
    @Bean
    @Primary
    public StringRedisTemplate mockStringRedisTemplate() {
        return Mockito.mock(StringRedisTemplate.class);
    }
}
