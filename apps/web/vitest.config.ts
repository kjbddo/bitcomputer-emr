import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@store": path.resolve(__dirname, "./src/store"),
      "@services": path.resolve(__dirname, "./src/services"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // 테스트마다 mock 호출 기록을 비운다.
    //
    // 이게 없으면 앞 테스트의 호출이 뒤 테스트의 not.toHaveBeenCalled() 로 새어
    // 들어간다. 실제로 부서 관리 테스트에서 그렇게 통과하던 케이스가 있었다.
    // mockResolvedValue 같은 구현 설정은 지우지 않으므로 기존 테스트에 영향 없다.
    clearMocks: true,
  },
});
