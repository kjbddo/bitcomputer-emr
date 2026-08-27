"use client";

import { useState, useEffect } from "react";
import { createUser, getAllUsers, setRole } from "@/services/admin";
import { User, Role } from "@/types/user";
import { Badge, Button, EmptyState, Field, Panel, Table } from "@/components/ui";
import styles from "./page.module.css";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [updatingRoles, setUpdatingRoles] = useState<Set<number>>(new Set());
  const [newUser, setNewUser] = useState({
    name: "",
    username: "",
    password: "",
    deptId: "1",
    role: Role.DOCTOR,
  });

  useEffect(() => {
    loadUsers();
  }, []);

  async function loadUsers() {
    setLoading(true);
    setError(null);
    try {
      const data = await getAllUsers();
      // 응답이 배열인 경우와 객체인 경우 모두 처리
      const userList = Array.isArray(data) ? data : (data?.users ?? []);
      setUsers(userList);
    } catch (err) {
      const message = err instanceof Error ? err.message : "유저 목록을 불러오는데 실패했습니다";
      setError(message);
      setUsers([]); // 에러 발생 시 빈 배열로 초기화
    } finally {
      setLoading(false);
    }
  }

  async function handleRoleChange(userId: number, newRole: Role) {
    setUpdatingRoles((prev) => new Set(prev).add(userId));
    try {
      await setRole(userId, newRole);
      // 성공 시 로컬 상태 업데이트
      setUsers((prevUsers) =>
        prevUsers.map((user) =>
          user.id === userId ? { ...user, role: newRole } : user
        )
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "역할 변경에 실패했습니다";
      setError(message);
    } finally {
      setUpdatingRoles((prev) => {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
    }
  }

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    const deptId = Number(newUser.deptId);
    if (!newUser.name.trim() || !newUser.username.trim() || !newUser.password.trim()) {
      setError("이름, 사용자명, 비밀번호를 모두 입력해주세요.");
      return;
    }
    if (!Number.isFinite(deptId) || deptId <= 0) {
      setError("부서 ID는 1 이상의 숫자여야 합니다.");
      return;
    }

    try {
      await createUser({
        name: newUser.name.trim(),
        username: newUser.username.trim(),
        password: newUser.password,
        deptId,
        role: newUser.role,
      });
      setSuccessMessage("직원이 추가되었습니다.");
      setNewUser({
        name: "",
        username: "",
        password: "",
        deptId: "1",
        role: Role.DOCTOR,
      });
      await loadUsers();
    } catch (err) {
      const message = err instanceof Error ? err.message : "직원 추가에 실패했습니다";
      setError(message);
    }
  }

  function getRoleLabel(role: Role): string {
    const roleMap: Record<Role, string> = {
      [Role.DEFAULT]: "일반",
      [Role.SUPER_USER]: "관리자",
      [Role.DOCTOR]: "의사",
      [Role.NURSE]: "간호사",
      [Role.RECEPTIONIST]: "접수원",
    };
    return roleMap[role] || role;
  }

  return (
    <div className={styles.container}>
      <div className={styles.wrapper}>
        {/* Header 가 h1(서비스명)을 이미 렌더하므로 이 화면의 제목은 h2 다 —
            Panel 의 title prop 이 h2 를 렌더한다. */}
        <Panel
          title="전체 유저 조회"
          actions={
            <Button type="button" variant="secondary" size="sm" onClick={loadUsers} disabled={loading} loading={loading}>
              새로고침
            </Button>
          }
        >
          {!loading && users && users.length > 0 && (
            <p className={styles.headerSubtitle}>
              총 <strong>{users.length}명</strong>의 유저가 등록되어 있습니다
            </p>
          )}
        </Panel>

        {error && (
          <div className={styles.errorMessage} role="alert">
            {error}
          </div>
        )}
        {successMessage && (
          <div className={styles.successMessage} role="status">
            {successMessage}
          </div>
        )}

        <Panel title="직원 추가">
          <form className={styles.createForm} onSubmit={handleCreateUser}>
            <Field label="이름" htmlFor="admin-new-user-name">
              <input
                id="admin-new-user-name"
                value={newUser.name}
                onChange={(e) => setNewUser((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="홍길동"
                required
              />
            </Field>
            <Field label="사용자명" htmlFor="admin-new-user-username">
              <input
                id="admin-new-user-username"
                value={newUser.username}
                onChange={(e) => setNewUser((prev) => ({ ...prev, username: e.target.value }))}
                placeholder="doctor01"
                required
              />
            </Field>
            <Field label="비밀번호" htmlFor="admin-new-user-password">
              <input
                id="admin-new-user-password"
                type="password"
                value={newUser.password}
                onChange={(e) => setNewUser((prev) => ({ ...prev, password: e.target.value }))}
                required
              />
            </Field>
            <Field label="부서 ID" htmlFor="admin-new-user-dept">
              <input
                id="admin-new-user-dept"
                type="number"
                min={1}
                value={newUser.deptId}
                onChange={(e) => setNewUser((prev) => ({ ...prev, deptId: e.target.value }))}
                required
              />
            </Field>
            <Field label="역할" htmlFor="admin-new-user-role">
              <select
                id="admin-new-user-role"
                value={newUser.role}
                onChange={(e) => setNewUser((prev) => ({ ...prev, role: e.target.value as Role }))}
              >
                <option value={Role.DOCTOR}>{getRoleLabel(Role.DOCTOR)}</option>
                <option value={Role.NURSE}>{getRoleLabel(Role.NURSE)}</option>
                <option value={Role.RECEPTIONIST}>{getRoleLabel(Role.RECEPTIONIST)}</option>
                <option value={Role.SUPER_USER}>{getRoleLabel(Role.SUPER_USER)}</option>
              </select>
            </Field>
            <Button type="submit" variant="primary" className={styles.createButton}>
              직원 추가
            </Button>
          </form>
        </Panel>

        <Panel title="유저 목록">
          {loading ? (
            <EmptyState title="로딩 중..." />
          ) : !users || users.length === 0 ? (
            <EmptyState title="등록된 유저가 없습니다" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">이름</th>
                  <th scope="col">사용자명</th>
                  <th scope="col">역할</th>
                  <th scope="col">부서 ID</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className={styles.tableCellId}>#{user.id}</td>
                    <td className={styles.tableCellName}>{user.name}</td>
                    <td>{user.username}</td>
                    <td>
                      <select
                        value={user.role}
                        onChange={(e) => handleRoleChange(user.id, e.target.value as Role)}
                        disabled={updatingRoles.has(user.id)}
                        aria-label={`${user.name} 역할 변경`}
                      >
                        <option value={Role.DEFAULT}>{getRoleLabel(Role.DEFAULT)}</option>
                        <option value={Role.SUPER_USER}>{getRoleLabel(Role.SUPER_USER)}</option>
                        <option value={Role.DOCTOR}>{getRoleLabel(Role.DOCTOR)}</option>
                        <option value={Role.NURSE}>{getRoleLabel(Role.NURSE)}</option>
                        <option value={Role.RECEPTIONIST}>{getRoleLabel(Role.RECEPTIONIST)}</option>
                      </select>
                    </td>
                    <td>
                      {user.deptId ? (
                        <Badge tone="neutral">{user.deptId}</Badge>
                      ) : (
                        <span className={styles.deptEmpty}>-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
    </div>
  );
}
