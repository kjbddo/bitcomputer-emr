"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import AuthLinkSwap from "@/components/common/AuthLink";
import { login } from "@/services/auth";
import { Button, Field, Panel } from "@/components/ui";
import styles from "./page.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login({ username, password });
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.shell}>
      <div className={styles.container}>
        <h1 className={styles.title}>로그인</h1>
        <Panel>
          <form onSubmit={handleSubmit} className={styles.form}>
            <Field label="사용자 ID" htmlFor="login-username" required>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="employee01"
              />
            </Field>
            <Field label="비밀번호" htmlFor="login-password" required>
              <input
                id="login-password"
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
              {loading ? "로그인 중..." : "로그인"}
            </Button>
          </form>
        </Panel>

        <AuthLinkSwap />
      </div>
    </div>
  );
}
