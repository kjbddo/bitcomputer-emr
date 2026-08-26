package com.example.bitcomputer.config;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.example.bitcomputer.Repository.UserRepository;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.slf4j.LoggerFactory;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

/**
 * Finding 1 검증: 삭제된 initializeSuperUser 시더가 예전에 만들어 둔 super/1234
 * 계정이 DB에 남아있을 때, 부팅 점검이 WARNING 로그를 남기는지 확인한다.
 */
@ExtendWith(MockitoExtension.class)
class DataInitializerTest {

    @Mock
    private UserRepository userRepository;

    private final PasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    private ListAppender<ILoggingEvent> logAppender;
    private Logger dataInitializerLogger;

    @BeforeEach
    void setUpLogCapture() {
        dataInitializerLogger = (Logger) LoggerFactory.getLogger(DataInitializer.class);
        logAppender = new ListAppender<>();
        logAppender.start();
        dataInitializerLogger.addAppender(logAppender);
    }

    @AfterEach
    void tearDownLogCapture() {
        dataInitializerLogger.detachAppender(logAppender);
    }

    @Test
    void warnsWhenSuperAccountStillHasDefaultPassword() {
        Employee legacySuperUser = new Employee();
        legacySuperUser.setUsername("super");
        legacySuperUser.setPassword(passwordEncoder.encode("1234"));
        legacySuperUser.setRole(Role.SUPER_USER);
        legacySuperUser.setDeptId(1);
        when(userRepository.findByUsername("super")).thenReturn(legacySuperUser);

        DataInitializer.checkLegacyDefaultSuperUserPassword(userRepository, passwordEncoder);

        assertEquals(1, logAppender.list.size());
        ILoggingEvent event = logAppender.list.get(0);
        assertEquals("WARN", event.getLevel().toString());
        assertTrue(event.getFormattedMessage().contains("super"));
        assertTrue(event.getFormattedMessage().contains("비밀번호를 변경"));
    }

    @Test
    void doesNotWarnWhenSuperAccountHasNonDefaultPassword() {
        Employee rotatedSuperUser = new Employee();
        rotatedSuperUser.setUsername("super");
        rotatedSuperUser.setPassword(passwordEncoder.encode("a-strong-rotated-password"));
        rotatedSuperUser.setRole(Role.SUPER_USER);
        rotatedSuperUser.setDeptId(1);
        when(userRepository.findByUsername("super")).thenReturn(rotatedSuperUser);

        DataInitializer.checkLegacyDefaultSuperUserPassword(userRepository, passwordEncoder);

        assertTrue(logAppender.list.isEmpty());
    }

    @Test
    void doesNotWarnWhenNoSuperAccountExists() {
        when(userRepository.findByUsername("super")).thenReturn(null);

        DataInitializer.checkLegacyDefaultSuperUserPassword(userRepository, passwordEncoder);

        assertTrue(logAppender.list.isEmpty());
    }
}
