package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.UserRepository;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
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

@Configuration
public class DataInitializer {

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

    @Bean
    @Order(2)
    public CommandLineRunner initializeSuperUser(UserRepository userRepository,
                                                 PasswordEncoder passwordEncoder) {
        return args -> {
            String username = "super";
            Employee existing = userRepository.findByUsername(username);
            if (existing == null) {
                Employee superUser = new Employee();
                superUser.setName("Super Admin");
                superUser.setDeptId(1);
                superUser.setRole(Role.SUPER_USER);
                superUser.setUsername(username);
                superUser.setPassword(passwordEncoder.encode("1234"));
                userRepository.save(superUser);
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
}


