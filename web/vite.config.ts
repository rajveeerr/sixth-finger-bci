import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // onnxruntime-web loads its wasm files itself; pre-bundling breaks those paths.
  optimizeDeps: { exclude: ["onnxruntime-web"] },
  server: { port: 5173 },
  // The 3D hand's chunk (three.js) is about 1 MB; it loads after the page has drawn.
  build: { chunkSizeWarningLimit: 1100 },
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
