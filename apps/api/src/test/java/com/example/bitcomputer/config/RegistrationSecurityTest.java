package com.example.bitcomputer.config;

import com.example.bitcomputer.Repository.UserRepository;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(TestRedisConfig.class)
class RegistrationSecurityTest {

    @Autowired private MockMvc mockMvc;
    @Autowired private UserRepository userRepository;

    private void register(String username, String requestedRole) throws Exception {
        mockMvc.perform(post("/api/user/register")
                .contentType("application/json")
                .content("""
                        {"name":"%s","deptId":1,"role":"%s","username":"%s","password":"Passw0rd!"}
                        """.formatted(username, requestedRole, username)));
    }

    @Test
    void selfRegistrationCannotClaimSuperUser() throws Exception {
        register("attacker", "SUPER_USER");
        Employee saved = userRepository.findByUsername("attacker");
        assertNotNull(saved);
        assertEquals(Role.DEFAULT, saved.getRole(),
                "공개 가입으로 SUPER_USER 를 얻을 수 있으면 RBAC 전체가 무력화된다");
    }

    @Test
    void selfRegistrationCannotClaimDoctor() throws Exception {
        register("fake.doctor", "DOCTOR");
        assertEquals(Role.DEFAULT, userRepository.findByUsername("fake.doctor").getRole());
    }

    @Test
    void selfRegistrationWithoutRoleIsDefault() throws Exception {
        mockMvc.perform(post("/api/user/register")
                .contentType("application/json")
                .content("""
                        {"name":"plain","deptId":1,"username":"plain","password":"Passw0rd!"}
                        """));
        assertEquals(Role.DEFAULT, userRepository.findByUsername("plain").getRole());
    }
}
