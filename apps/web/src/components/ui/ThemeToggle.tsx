"use client";

import { useTheme, type ThemeChoice } from "@/components/theme/ThemeProvider";
import styles from "./ThemeToggle.module.css";

const ORDER: ThemeChoice[] = ["system", "light", "dark"];

const LABEL: Record<ThemeChoice, string> = {
  system: "시스템 설정",
  light: "라이트",
  dark: "다크",
};

function nextOf(current: ThemeChoice): ThemeChoice {
  return ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
}

function Icon({ theme }: { theme: ThemeChoice }) {
  if (theme === "light") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
      </svg>
    );
  }
  if (theme === "dark") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M8 21h8" />
    </svg>
  );
}

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = nextOf(theme);

  return (
    <button
      type="button"
      className={styles.toggle}
      onClick={() => setTheme(next)}
      aria-label={`테마: ${LABEL[theme]}. 클릭하면 ${LABEL[next]}`}
    >
      <Icon theme={theme} />
    </button>
  );
}
