package com.example.bitcomputer.config;

import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.jwt.JwtTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
@ActiveProfiles("test")
@org.springframework.context.annotation.Import({TestRedisConfig.class, TestRabbitConfig.class})
class SecurityConfigTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtTokenProvider jwtTokenProvider;

    private jakarta.servlet.http.Cookie cookieFor(Role role) {
        String token = jwtTokenProvider.generateAccessToken("tester", role);
        return new jakarta.servlet.http.Cookie(CookieFactory.ACCESS_TOKEN_COOKIE, token);
    }

    @Test
    void patientApiRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/patients/1"))
               .andExpect(status().isUnauthorized());
    }

    @Test
    void loginEndpointIsPublic() throws Exception {
        mockMvc.perform(post("/api/user/login")
                       .contentType("application/json")
                       .content("{\"username\":\"none\",\"password\":\"none\"}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(401)));
    }

    @Test
    void actuatorHealthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
               .andExpect(status().isOk());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void receptionistCannotCallAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.RECEPTIONIST))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void nurseCannotCallAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.NURSE))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().isForbidden());
    }

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void doctorReachesAgentApi() throws Exception {
        mockMvc.perform(post("/api/agent/prescription/recommend")
                       .cookie(cookieFor(Role.DOCTOR))
                       .with(csrf())
                       .contentType("application/json")
                       .content("{}"))
               .andExpect(status().is(org.hamcrest.Matchers.not(403)));
    }

    @Test
    void defaultRoleIsDeniedEverywhere() throws Exception {
        mockMvc.perform(get("/api/patients/1")
                       .cookie(cookieFor(Role.DEFAULT)))
               .andExpect(status().isForbidden());
    }

    @Test
    void superUserOnlyForRoleManagement() throws Exception {
        mockMvc.perform(get("/api/super/employees")
                       .cookie(cookieFor(Role.DOCTOR)))
               .andExpect(status().isForbidden());
    }
}
