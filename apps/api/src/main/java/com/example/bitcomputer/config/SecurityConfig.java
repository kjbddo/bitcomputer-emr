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
import org.springframework.security.web.authentication.session.NullAuthenticatedSessionStrategy;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
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
                // Spring Security 6 기본값인 XorCsrfTokenRequestAttributeHandler 는
                // X-XSRF-TOKEN 헤더 값이 BREACH 방지용으로 XOR 마스킹되어 있다고
                // 가정하고 이를 디코딩한 뒤 실제 토큰과 비교한다. 그런데
                // CookieCsrfTokenRepository 는 XSRF-TOKEN 쿠키에 마스킹되지 않은
                // 원문(raw) 토큰을 그대로 굽는다. 그 결과 "쿠키 값을 그대로 읽어
                // 헤더에 실어 보내는" 표준 SPA 더블서브밋 패턴(axios 의
                // xsrfCookieName/xsrfHeaderName, 그리고 이 프로젝트의
                // apps/web/src/services/http/client.ts 가 정확히 이렇게 동작한다)이
                // 매번 403 으로 거부된다.
                //
                // CsrfTokenRequestAttributeHandler 는 헤더 값을 마스킹 해제 없이
                // 원문 그대로 비교하므로 쿠키가 실제로 담고 있는 값과 일치한다.
                // BREACH 완화를 포기하는 대신 쿠키 기반 더블서브밋 SPA 와 맞물리게
                // 하는 것이며, Spring 공식 문서가 이 조합을 위해 안내하는 표준
                // 구성이다.
                .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
                .ignoringRequestMatchers("/api/user/login", "/api/user/register")
                // 두 번째(독립적인) 결함: HttpSecurity.csrf(...) 는 항상
                // CsrfAuthenticationStrategy 를 SessionManagementConfigurer 에 등록한다
                // (세션 고정 공격을 막기 위해 "새로 인증됐다" 싶으면 CSRF 쿠키를
                // 지우고 새로 굽는다). 문제는 "새로 인증됐다"의 판정 기준이
                // SessionManagementFilter 의 securityContextRepository.containsContext(request)
                // 인데, SessionCreationPolicy.STATELESS 에서는 이게 NullSecurityContextRepository
                // 라 언제나 false 다. 게다가 이 앱은 세션 로그인이 아니라 JwtAuthenticationFilter
                // 가 "매 요청마다" 쿠키의 JWT 를 읽어 SecurityContext 를 채우므로,
                // SessionManagementFilter 입장에서는 "인증된 모든 요청"이 다 "방금 새로
                // 로그인함"으로 보인다. 그 결과 CsrfAuthenticationStrategy 가 인증된 요청마다
                // (GET 포함) XSRF-TOKEN 쿠키를 삭제→재발급 시도하고, 그 삭제가 응답에
                // 그대로 실려 나가 SPA 가 들고 있던 토큰이 매 요청 끝나자마자 무효화된다.
                // 실전에서는 로그인 직후 첫 조회(GET) 한 번만으로 이미 쓰기 요청이 깨진다
                // — csrfTokenRequestHandler 만 고쳐서는 해결되지 않는 별개의 결함이다.
                //
                // 트레이드오프: NullAuthenticatedSessionStrategy 로 바꾸면 "로그인 시 CSRF
                // 토큰 회전" 방어가 빠진다. 그런데 이 앱의 실제 로그인(/api/user/login)은
                // Spring 의 AuthenticationManager 를 거치지 않는 커스텀 컨트롤러라
                // CsrfAuthenticationStrategy 가 애초에 "진짜 로그인 시점"을 구분해 회전시킨
                // 적이 없다 — 그냥 인증된 모든 요청에서 무차별적으로 발동해 왔을 뿐이다.
                // 즉 이 옵션을 끄는 것은 "정상 작동하던 로그인 시 회전 방어"를 포기하는
                // 것이 아니라, 애초에 의도대로 동작한 적 없는 오작동을 끄는 것이다.
                .sessionAuthenticationStrategy(new NullAuthenticatedSessionStrategy())
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
                .requestMatchers("/api/admin/**", "/api/audit/**").hasRole("SUPER_USER")

                // ── AI 기능: 임상 판단이 개입하므로 DOCTOR 전용 ──
                .requestMatchers("/api/agent/**", "/api/ai/**",
                                 "/api/validation-jobs/**", "/api/radiology/**")
                    .hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 진료 기록 작성: DOCTOR ──
                .requestMatchers(HttpMethod.POST,   "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.PUT,    "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")
                .requestMatchers(HttpMethod.DELETE, "/api/histories/**").hasAnyRole("DOCTOR", "SUPER_USER")

                // ── AI 검증 결과 조회: AI 기능은 DOCTOR 전용이다(5.3) ──
                // HistoryDiagnoseController/HistoryDiseaseController/ValidationResultController 는
                // 모두 "/api/histories" 아래 매핑돼 있다("/api/history-diagnoses",
                // "/api/history-diseases" 는 실제로 존재하지 않는 경로였다 — 아래 GET 매처들이
                // 그 자리를 대신한다). 쓰기(POST/PUT/DELETE)는 위 "/api/histories/**" 규칙으로
                // 이미 DOCTOR 전용이다.
                .requestMatchers(HttpMethod.GET, "/api/histories/*/validation_results")
                    .hasAnyRole("DOCTOR", "SUPER_USER")

                // ── 처방·상병 조회, 진료 이력 검색: NURSE 도 가능(원무는 불가, 5.3) ──
                .requestMatchers(HttpMethod.GET,
                                 "/api/histories/*/get_diagnoses",
                                 "/api/histories/*/get_diseases",
                                 "/api/histories/search_history/*")
                    .hasAnyRole("NURSE", "DOCTOR", "SUPER_USER")

                // ── 환자·대기: 원무도 가능 ──
                .requestMatchers("/api/patients/**", "/api/waiting/**")
                    .hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")

                // ── 마스터 코드 조회 ──
                .requestMatchers(HttpMethod.GET, "/api/diseases/**", "/api/diagnoses/**")
                    .hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")

                // ── 나머지 업무 API: 인증된 실제 역할이면 통과 (DEFAULT 제외) ──
                .anyRequest().hasAnyRole("RECEPTIONIST", "NURSE", "DOCTOR", "SUPER_USER")
            )
            // jwtAuthenticationFilter 를 CsrfFilter 보다 앞에 둔다(원래는
            // UsernamePasswordAuthenticationFilter 보다만 앞이었는데, 그 위치는
            // CsrfFilter 보다 뒤다). CsrfFilter 가 먼저 돌면 CSRF 토큰이 없거나
            // 틀린 요청은 SecurityContext 가 비어 있는 채로 거부돼, RestAccessDeniedHandler
            // 가 "누가" 시도했는지 알 수 없다(I2). CsrfFilter 자체는 인증 여부와
            // 무관하게 쿠키의 토큰만 검증하므로, 인증 필터를 앞으로 옮겨도 CSRF
            // 검증 로직에는 영향이 없다 — 대안으로 핸들러 안에서 쿠키의 JWT 를
            // 직접 다시 파싱하는 방법도 검토했지만, JwtAuthenticationFilter 가 이미
            // 하는 일을 또 한 곳에서 중복 구현하게 되어 이 쪽을 택했다.
            .addFilterBefore(jwtAuthenticationFilter, CsrfFilter.class)
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
