import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import ThemeProvider from "../ThemeProvider";
import ThemeToggle from "@/components/ui/ThemeToggle";
import { THEME_STORAGE_KEY } from "@/app/theme-script";

function renderToggle() {
  return render(
    <ThemeProvider>
      <ThemeToggle />
    </ThemeProvider>
  );
}

describe("ThemeProvider / ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("저장값이 없으면 system 상태로 시작하고 data-theme 속성을 붙이지 않는다", () => {
    renderToggle();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("저장된 dark 를 복원한다", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderToggle();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("system -> light -> dark -> system 을 순환한다", () => {
    renderToggle();
    const button = screen.getByRole("button");

    fireEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");

    fireEvent.click(button);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");

    fireEvent.click(button);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it("현재 상태를 aria-label 로 노출한다", () => {
    renderToggle();
    expect(screen.getByRole("button").getAttribute("aria-label")).toContain("시스템");
  });
});
