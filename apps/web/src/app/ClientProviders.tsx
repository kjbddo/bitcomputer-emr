"use client";

import ThemeProvider from "@/components/theme/ThemeProvider";

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}
