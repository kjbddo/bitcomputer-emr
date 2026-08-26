package com.example.bitcomputer.config;

import com.example.bitcomputer.jwt.JwtAuthenticationFilter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.Arrays;
import java.util.List;

@Configuration
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final CsrfCookieFilter csrfCookieFilter;
    private final RestAccessDeniedHandler restAccessDeniedHandler;
    private final String allowedOrigins;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter,
                          CsrfCookieFilter csrfCookieFilter,
                          RestAccessDeniedHandler restAccessDeniedHandler,
                          @Value("${cors.allowed-origins}") String allowedOrigins) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.csrfCookieFilter = csrfCookieFilter;
        this.restAccessDeniedHandler = restAccessDeniedHandler;
        this.allowedOrigins = allowedOrigins;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(cors -> cors.configurationSource(corsConfigurationSource()))
            .csrf(csrf -> csrf
                .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
                .ignoringRequestMatchers("/api/user/login", "/api/user/register")
            )
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(e -> e
                .authenticationEntryPoint(
                        new HttpStatusEntryPoint(org.springframework.http.HttpStatus.UNAUTHORIZED))
                .accessDeniedHandler(restAccessDeniedHandler)
            )
            .authorizeHttpRequests(auth -> auth
                // ── 공개 ──
                .requestMatchers("/api/user/login", "/api/user/register").permitAll()
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()

                // ── SUPER_USER 전용 ──
                .requestMatchers("/api/super/**", "/api/audit/**").hasRole("SUPER_USER")

                // ── AI 기능: 임상 판단이 개입하므로 DOCTOR 전용 ──
                .requestMatchers("/api/agent/**", "/api/ai/**",
                                 "/api/validation-jobs/**", "/api/radiology/**")
                    .hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 진료 기록 작성: DOCTOR ──
                .requestMatchers(HttpMethod.POST,   "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.PUT,    "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.DELETE, "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 처방 등록·수정: DOCTOR / 조회: NURSE 도 가능 ──
                .requestMatchers(HttpMethod.POST,   "/api/history-diagnoses/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.PUT,    "/api/history-diagnoses/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.DELETE, "/api/history-diagnoses/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.GET,    "/api/history-diagnoses/**")
                    .hasAnyRole("DOCTOR", "NURSE", "SUPER_USER")

                // ── 상병 등록·수정: DOCTOR ──
                .requestMatchers(HttpMethod.POST,   "/api/history-diseases/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.PUT,    "/api/history-diseases/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.DELETE, "/api/history-diseases/**").hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 환자·대기: 원무도 가능 ──
                .requestMatchers("/api/patients/**", "/api/waiting/**")
                    .hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")

                // ── 마스터 코드 조회 ──
                .requestMatchers(HttpMethod.GET, "/api/diseases/**", "/api/diagnoses/**")
                    .hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")

                // ── 나머지 업무 API: 인증된 실제 역할이면 통과 (DEFAULT 제외) ──
                .anyRequest().hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")
            )
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
            .addFilterAfter(csrfCookieFilter, CsrfFilter.class);

        return http.build();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of(allowedOrigins.split("\s*,\s*")));
        configuration.setAllowedMethods(Arrays.asList("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("*"));
        configuration.setAllowCredentials(true);
        configuration.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }
}
