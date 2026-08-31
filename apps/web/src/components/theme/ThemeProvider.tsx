"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { THEME_STORAGE_KEY } from "@/app/theme-script";

export type ThemeChoice = "system" | "light" | "dark";

interface ThemeContextValue {
  theme: ThemeChoice;
  setTheme: (next: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredTheme(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function applyTheme(next: ThemeChoice) {
  const root = document.documentElement;
  if (next === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", next);
  }
}

export default function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeChoice>("system");

  // 서버 렌더에는 localStorage 가 없다. 마운트 후 실제 값으로 맞춘다.
  useEffect(() => {
    const stored = readStoredTheme();
    setThemeState(stored);
    applyTheme(stored);
  }, []);

  const setTheme = useCallback((next: ThemeChoice) => {
    setThemeState(next);
    applyTheme(next);
    try {
      if (next === "system") {
        localStorage.removeItem(THEME_STORAGE_KEY);
      } else {
        localStorage.setItem(THEME_STORAGE_KEY, next);
      }
    } catch {
      // 저장에 실패해도 이번 세션의 화면은 이미 바뀌었다.
    }
  }, []);

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme 은 ThemeProvider 안에서만 쓸 수 있습니다.");
  }
  return ctx;
}
