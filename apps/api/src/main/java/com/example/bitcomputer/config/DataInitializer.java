package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.UserRepository;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
// 임시 더미 데이터 추가하는 코드이니깐 나중에 dept 구현 시에 없애야 함!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

@Slf4j
@Configuration
public class DataInitializer {

    /** DataInitializer 가 과거에 심었던 기본 SUPER_USER 계정의 아이디/비밀번호. 삭제된 시더의 흔적을 점검할 때만 참조한다. */
    static final String LEGACY_DEFAULT_SUPERUSER_USERNAME = "super";
    static final String LEGACY_DEFAULT_SUPERUSER_PASSWORD = "1234";

    @Bean
    @Order(1)
    public CommandLineRunner initializeDummyDept(JdbcTemplate jdbcTemplate) {
        return args -> {
            // dept 테이블에 id=1 이 없으면 생성 (UNASSIGNED)
            String upsertSql = "INSERT INTO dept (id, dept) VALUES (1, 'UNASSIGNED') " +
                    "ON DUPLICATE KEY UPDATE dept = VALUES(dept)";
            jdbcTemplate.update(upsertSql);
        };
    }

    /** JPA ddl-auto=update 가 새 컬럼을 안 만든 기존 DB용 — disease.name_en 보장 (MySQL) */
    @Bean
    public CommandLineRunner ensureDiseaseNameEnColumn(JdbcTemplate jdbcTemplate) {
        return args -> {
            Integer tables = jdbcTemplate.queryForObject(
                    """
                            SELECT COUNT(*) FROM information_schema.TABLES
                            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'disease'
                            """,
                    Integer.class
            );
            if (tables == null || tables == 0) {
                return;
            }
            Integer cols = jdbcTemplate.queryForObject(
                    """
                            SELECT COUNT(*) FROM information_schema.COLUMNS
                            WHERE TABLE_SCHEMA = DATABASE()
                              AND TABLE_NAME = 'disease'
                              AND COLUMN_NAME = 'name_en'
                            """,
                    Integer.class
            );
            if (cols != null && cols == 0) {
                jdbcTemplate.execute("ALTER TABLE disease ADD COLUMN name_en TEXT NULL");
            }
        };
    }

    /**
     * 최초 SUPER_USER 시드.
     *
     * 공개 가입은 항상 DEFAULT 이므로 역할을 부여할 주체가 하나는 있어야 한다.
     * BOOTSTRAP_SUPERUSER_PASSWORD 가 비어 있으면 만들지 않는다 — 운영에서
     * 기본 비밀번호 계정이 생기는 것을 막기 위해서다.
     */
    @Bean
    @Order(2)
    public CommandLineRunner initializeBootstrapSuperUser(UserRepository userRepository,
                                                          PasswordEncoder passwordEncoder) {
        return args -> {
            String password = System.getenv("BOOTSTRAP_SUPERUSER_PASSWORD");
            if (password == null || password.isBlank()) {
                return;
            }
            if (userRepository.findByUsername("admin") != null) {
                return;
            }
            Employee admin = new Employee();
            admin.setName("bootstrap admin");
            admin.setDeptId(1);
            admin.setUsername("admin");
            admin.setPassword(passwordEncoder.encode(password));
            admin.setRole(Role.SUPER_USER);
            userRepository.save(admin);
        };
    }

    /**
     * 예전 initializeSuperUser 시더가 심었던 super/1234 계정이 아직 남아있는지 부팅 시 점검한다.
     *
     * 이 시더 자체는 삭제됐지만, 이미 시더로 생성된 계정이 존재하는 DB에는 아무 영향이 없다.
     * 부팅 때마다 계정을 지우거나 비밀번호를 바꾸는 것은 데이터 파괴이므로 하지 않고,
     * 대신 운영자가 알아차릴 수 있도록 경고만 남긴다.
     */
    @Bean
    @Order(3)
    public CommandLineRunner warnIfLegacyDefaultSuperUserPasswordActive(UserRepository userRepository,
                                                                        PasswordEncoder passwordEncoder) {
        return args -> checkLegacyDefaultSuperUserPassword(userRepository, passwordEncoder);
    }

    /** 테스트에서 직접 호출할 수 있도록 CommandLineRunner 본체를 별도 메서드로 분리. */
    static void checkLegacyDefaultSuperUserPassword(UserRepository userRepository, PasswordEncoder passwordEncoder) {
        Employee existing = userRepository.findByUsername(LEGACY_DEFAULT_SUPERUSER_USERNAME);
        if (existing == null) {
            return;
        }
        if (existing.getPassword() != null
                && passwordEncoder.matches(LEGACY_DEFAULT_SUPERUSER_PASSWORD, existing.getPassword())) {
            log.warn("보안 경고: '{}' 계정이 기본 비밀번호('{}')를 그대로 사용 중입니다. "
                            + "SUPER_USER 권한으로 모든 환자 데이터·역할 배정에 접근할 수 있는 상태이니, "
                            + "즉시 비밀번호를 변경하거나 해당 계정을 삭제하세요.",
                    LEGACY_DEFAULT_SUPERUSER_USERNAME, LEGACY_DEFAULT_SUPERUSER_PASSWORD);
        }
    }
}


