package com.example.bitcomputer.serviceImpl;

import com.example.bitcomputer.model.UserRegisterDTO;
import com.example.bitcomputer.jwt.TokenInfo;
import com.example.bitcomputer.model.LoginRequestDTO;
import com.example.bitcomputer.service.UserService;
import com.example.bitcomputer.Repository.UserRepository;
import com.example.bitcomputer.Repository.DeptRepository;
import com.example.bitcomputer.entity.Employee;
import com.example.bitcomputer.entity.Role;
import com.example.bitcomputer.exception.DuplicateUsernameException;
import com.example.bitcomputer.exception.InvalidCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import com.example.bitcomputer.jwt.JwtTokenProvider;

@Service
public class UserServiceImpl implements UserService {
    private final UserRepository userRepository;
    private final DeptRepository deptRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;
    private final TokenBlacklistService tokenBlacklistService;

    public UserServiceImpl(UserRepository userRepository, DeptRepository deptRepository,
    PasswordEncoder passwordEncoder, JwtTokenProvider jwtTokenProvider,
    TokenBlacklistService tokenBlacklistService) {
        this.userRepository = userRepository;
        this.deptRepository = deptRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtTokenProvider = jwtTokenProvider;
        this.tokenBlacklistService = tokenBlacklistService;
    }

    @Override
    public void registerUser(UserRegisterDTO userRegisterDTO) {
        Employee employee = new Employee();
        if (userRepository.findByUsername(userRegisterDTO.getUsername()) != null) {
            throw new DuplicateUsernameException("Username already exists");
        }
        employee.setName(userRegisterDTO.getName());
        int requestedDeptId = userRegisterDTO.getDeptId();
        int defaultDeptId = 1; // 더미 부서 ID
        int deptId = requestedDeptId > 0 ? requestedDeptId : defaultDeptId;
        // FK 제약을 DB 에 맡기면 500 + SQL 내용 노출로 이어진다(I2b). 저장 전에
        // 존재 여부를 검증해 400 으로 되돌린다.
        if (!deptRepository.existsById(deptId)) {
            throw new IllegalArgumentException("존재하지 않는 부서입니다. deptId=" + deptId);
        }
        employee.setDeptId(deptId);
        // 공개 가입은 항상 DEFAULT 다. 요청 본문의 role 은 신뢰하지 않는다.
        // 역할 부여는 SUPER_USER 가 /api/super/set_role/{id} 또는
        // /api/super/create_user 로만 할 수 있다.
        employee.setRole(Role.DEFAULT);
        employee.setUsername(userRegisterDTO.getUsername());
        employee.setPassword(passwordEncoder.encode(userRegisterDTO.getPassword()));
        userRepository.save(employee);
    }

    @Override
    public TokenInfo loginUser(LoginRequestDTO loginRequestDTO) {
        // 사용자 부재/비밀번호 불일치를 동일한 예외·메시지로 던져 사용자 존재
        // 여부를 노출하지 않는다.
        Employee employee = userRepository.findByUsername(loginRequestDTO.getUsername());
        if (employee == null) {
            throw new InvalidCredentialsException("Invalid username or password");
        }
        if (!passwordEncoder.matches(loginRequestDTO.getPassword(), employee.getPassword())) {
            throw new InvalidCredentialsException("Invalid username or password");
        }
        String accessToken = jwtTokenProvider.generateAccessToken(
                employee.getUsername(), employee.getRole());
        String refreshToken = jwtTokenProvider.generateRefreshToken(employee.getUsername());
        return new TokenInfo("Bearer", accessToken, refreshToken);
    }

    @Override
    public void logoutUser(String accessToken) {
        // 만료 시간을 밀리초에서 초로 변환하여 전달
        long expirationTime = (jwtTokenProvider.getExpiration(accessToken) - System.currentTimeMillis()) / 1000;
        if (expirationTime > 0) {
            tokenBlacklistService.blacklistToken(accessToken, expirationTime);
        }
    }
}
