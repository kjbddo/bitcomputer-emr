import { Role } from "@/types/user";
import { post, get } from "./http/client";
import { clearClientAuthState } from "@/lib/auth/token";

export interface LoginRequestBody {
  username: string;
  password: string;
}

export interface LoginResponseBody {
  grantType: string;
  accessToken: string;
  refreshToken: string;
}

export interface SignupRequestBody {
  name: string;
  deptId?: string;
  role: string;
  username: string;
  password: string;
}

export interface CurrentUserProfile {
  id: number;
  name: string;
  deptId: number;
  role: Role;
  username: string;
}

export interface DoctorProfile {
  id: number;
  name: string;
  deptId: number;
  username: string;
}

export async function login(body: LoginRequestBody): Promise<LoginResponseBody> {
  // 서버가 HttpOnly 쿠키로 access token 을 내려준다. 응답 본문에는 토큰이
  // 없으므로(Task 8) 여기서는 로그인 성공 여부만 확인한다.
  return post<LoginResponseBody, LoginRequestBody>("/api/user/login", body);
}

export async function signup(body: SignupRequestBody): Promise<void> {
  await post<void, SignupRequestBody>("/api/user/register", body);
}

export async function logout(): Promise<void> {
  try {
    // 서버가 쿠키(HttpOnly access_token)를 읽어 Redis 블랙리스트에 등록하고
    // Set-Cookie 로 만료시킨다. 요청 바디는 필요 없다.
    await post<void>("/api/user/logout");
  } finally {
    clearClientAuthState();
  }
}

export async function getRole(): Promise<Role> {  
  const data = await get<Role>("/api/patients/get_role");
  return data;
}

export async function getMe(): Promise<CurrentUserProfile> {
  return get<CurrentUserProfile>("/api/patients/get_me");
}

export async function getDoctors(): Promise<DoctorProfile[]> {
  return get<DoctorProfile[]>("/api/patients/doctors");
}
