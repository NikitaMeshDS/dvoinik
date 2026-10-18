import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// VITE_SHOWCASE=1 собирает онлайн-витрину: один JS-файл и относительные пути.
const showcase = Boolean(process.env.VITE_SHOWCASE);
export default defineConfig({
  plugins: [react()],
  base: showcase ? "./" : "/",
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": "http://127.0.0.1:8501",
      "/download": "http://127.0.0.1:8501",
    },
  },
  build: showcase
    ? {
        outDir: "dist-showcase",
        rollupOptions: { output: { inlineDynamicImports: true } },
      }
    : { outDir: "dist" },
});
