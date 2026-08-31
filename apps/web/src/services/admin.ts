import { get, post, put } from "./http/client";
import { Role, User } from "@/types/user";
import { Dept } from "@/types/dept";
import { AuditFilter, AuditLog, Page } from "@/types/audit";

interface GetAllUsersResponseBody {
  totalUserCount: number;
  users: User[];
}

export interface CreateUserRequestBody {
  name: string;
  deptId: number;
  role: Role;
  username: string;
  password: string;
}

export async function getAllUsers(): Promise<GetAllUsersResponseBody | User[]> {
  return get<GetAllUsersResponseBody | User[]>("/api/admin/users");
}

export async function createUser(body: CreateUserRequestBody): Promise<void> {
  await post<void, CreateUserRequestBody>("/api/admin/users", body);
}

export async function setRole(id: number, role: Role): Promise<void> {
  await put<void, { role: Role }>(`/api/admin/users/${id}/role`, { role });
}

export async function getDepts(): Promise<Dept[]> {
  return get<Dept[]>("/api/depts");
}

export async function createDept(dept: string): Promise<Dept> {
  return post<Dept, { dept: string }>("/api/admin/depts", { dept });
}

export async function renameDept(id: number, dept: string): Promise<Dept> {
  return put<Dept, { dept: string }>(`/api/admin/depts/${id}`, { dept });
}

export async function getAuditLogs(filter: AuditFilter): Promise<Page<AuditLog>> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filter)) {
    if (value !== undefined && value !== null && value !== "") {
      params.append(key, String(value));
    }
  }
  const qs = params.toString();
  return get<Page<AuditLog>>(`/api/audit/logs${qs ? `?${qs}` : ""}`);
}
