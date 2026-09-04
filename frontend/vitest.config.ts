import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  // Unit tests here are pure logic; skip the app's Tailwind v4 PostCSS pipeline.
  css: { postcss: { plugins: [] } },
  test: {
    environment: "node",
    css: false,
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
