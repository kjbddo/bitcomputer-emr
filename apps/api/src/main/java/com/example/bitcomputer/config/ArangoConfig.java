package com.example.bitcomputer.config;

import com.arangodb.ArangoDB;
import com.arangodb.springframework.annotation.EnableArangoRepositories;
import com.arangodb.springframework.config.ArangoConfiguration;
import org.springframework.beans.factory.annotation.Value;
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
@EnableArangoRepositories(basePackages = "com.example.bitcomputer.Repository.arango")
public class ArangoConfig implements ArangoConfiguration {
    @Value("${arangodb.hosts}")
    private String hosts;

    @Value("${arangodb.user}")
    private String user;

    @Value("${arangodb.password}")
    private String password;

    @Value("${arangodb.database}")
    private String database;

    @Override
    public ArangoDB.Builder arango() {
        String[] hostPort = hosts.split(":");
        return new ArangoDB.Builder()
                .host(hostPort[0], Integer.parseInt(hostPort[1]))
                .user(user)
                .password(password);
    }

    @Override
    public String database() {
        return database;
    }
}
