package com.example.bitcomputer.config;

import org.mockito.Mockito;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

// RabbitAutoConfiguration 을 application-test.properties 에서 제외하면 실제 브로커에
// 연결을 시도하는 CachingConnectionFactory 와, 컨텍스트 기동 시 큐를 선언하려는
// RabbitAdmin 이 함께 사라진다. 다만 ValidationRabbitConfig 가 수동 @Bean 으로
// ConnectionFactory 를 주입받아 RabbitTemplate/리스너 컨테이너를 만들기 때문에,
// 그 빈이 없으면 컨텍스트 기동 자체가 실패한다. 여기서 목(mock) ConnectionFactory 를
// 대신 공급해 브로커 없이도 컨텍스트가 뜨게 한다 — TestRedisConfig 와 동일한 패턴이다.
@TestConfiguration
public class TestRabbitConfig {

    @Bean
    public ConnectionFactory connectionFactory() {
        return Mockito.mock(ConnectionFactory.class);
    }
}
