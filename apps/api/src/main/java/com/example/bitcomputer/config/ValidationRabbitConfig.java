package com.example.bitcomputer.config;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;

/**
 * AI 가 켜져 있을 때만 구성한다(DR 구성에서는 이 배선 전체가 사라진다).
 *
 * <p>{@code matchIfMissing = true} 다 — 값이 없으면 켠다. 설정 실수 하나로
 * 전체 배포의 AI 가 조용히 사라지는 쪽보다, 끄는 것이 명시적 선택이어야 한다
 * ({@link AiFeatures} 참고).
 */
@ConditionalOnProperty(name = "features.ai.enabled", havingValue = "true", matchIfMissing = true)
@Configuration
public class ValidationRabbitConfig {

    @Bean
    public Queue validationRequestQueue(
            @Value("${validation.rabbitmq.request-queue:validation.prescription.request}") String queueName) {
        return new Queue(queueName, true);
    }

    @Bean
    public Queue validationResultQueue(
            @Value("${validation.rabbitmq.result-queue:validation.prescription.result}") String queueName) {
        return new Queue(queueName, true);
    }

    @Bean
    public MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory, MessageConverter jsonMessageConverter) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(jsonMessageConverter);
        return template;
    }

    @Bean
    public SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            ConnectionFactory connectionFactory,
            MessageConverter jsonMessageConverter) {
        SimpleRabbitListenerContainerFactory factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(jsonMessageConverter);
        return factory;
    }
}
