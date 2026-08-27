"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getMe } from "@/services/auth";
import { ThemeToggle } from "@/components/ui";
import styles from "./Header.module.css";

interface HeaderProps {
  activeMenu?: string;
}

export default function Header({ activeMenu }: HeaderProps) {
  void activeMenu;

  const [username, setUsername] = useState("");

  useEffect(() => {
    let cancelled = false;

    getMe()
      .then((me) => {
        if (!cancelled) setUsername(me.name);
      })
      .catch(() => {
        if (!cancelled) setUsername("");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header className={styles.header}>
      <div className={styles.leftSection}>
        <h1 className={styles.title}>BitComputer EMR</h1>
      </div>

      <div className={styles.rightSection}>
        <ThemeToggle />
        {username && <span className={styles.username}>{username}</span>}
        <Link href="/login" className={styles.button}>
          로그아웃
        </Link>
      </div>
    </header>
  );
}
