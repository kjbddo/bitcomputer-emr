"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Header from "@/components/Header";
import { getRole } from "@/services/auth";
import { Role } from "@/types/user";
import styles from "./layout.module.css";

const NAV = [
  { href: "/admin/audit", label: "감사 로그" },
  { href: "/admin/depts", label: "부서 관리" },
  { href: "/admin/users", label: "직원 관리" },
];

/**
 * 관리자 콘솔 공통 레이아웃.
 *
 * 역할 확인을 여기서 한 번만 하고 하위 화면은 반복하지 않는다.
 * 이것은 UX 장치이며 방어 계층이 아니다 — 실제 권한 판정은 서버가 하고,
 * SUPER_USER 가 아니면 /api/admin/** 이 403 을 반환한다.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    getRole()
      .then((role) => setAllowed(role === Role.SUPER_USER))
      .catch(() => setAllowed(false));
  }, []);

  if (allowed === null) {
    return <div className={styles.gate}>확인 중…</div>;
  }

  if (!allowed) {
    return <div className={styles.gate}>관리자만 접근할 수 있습니다.</div>;
  }

  return (
    <div className={styles.page}>
      <Header />
      <div className={styles.shell}>
        <nav className={styles.sidebar}>
          {/* Header 가 h1(서비스명)을 이미 렌더하므로 여기는 h2 다. */}
          <h2 className={styles.title}>관리자 콘솔</h2>
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
              className={
                pathname === item.href
                  ? `${styles.navLink} ${styles.navLinkActive}`
                  : styles.navLink
              }
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}
