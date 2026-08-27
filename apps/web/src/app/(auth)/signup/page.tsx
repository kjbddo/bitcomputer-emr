"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signup } from "@/services/auth";
import { Button, Field, Panel } from "@/components/ui";
import styles from "./page.module.css";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await signup({
        name,
        username,
        password,
        role,
      });
      router.push("/login");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "회원가입에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.shell}>
      <div className={styles.container}>
        <h1 className={styles.title}>회원가입</h1>
        <Panel>
          <form onSubmit={handleSubmit} className={styles.form}>
            <Field label="이름" htmlFor="signup-name" required>
              <input
                id="signup-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="홍길동"
              />
            </Field>
            <Field label="사용자 ID" htmlFor="signup-username" required>
              <input
                id="signup-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="employee01"
              />
            </Field>
            <Field label="직무" htmlFor="signup-role" required>
              <select id="signup-role" value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="" disabled>
                  직무를 선택하세요
                </option>
                <option value="DOCTOR">의사</option>
                <option value="NURSE">간호사</option>
                <option value="RECEPTIONIST">접수원</option>
              </select>
            </Field>
            <Field label="비밀번호" htmlFor="signup-password" required>
              <input
                id="signup-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </Field>

            {error && (
              <p className={styles.formAlert} role="alert">
                {error}
              </p>
            )}

            <Button type="submit" variant="primary" loading={loading}>
              {loading ? "가입 중..." : "회원가입"}
            </Button>
          </form>
        </Panel>

        <p className={styles.footer}>
          이미 계정이 있으신가요? <Link href="/login">로그인</Link>
        </p>
      </div>
    </div>
  );
}
