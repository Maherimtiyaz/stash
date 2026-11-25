import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The FastAPI server serves the built files at /app. In development, Vite proxies API calls to it.
export default defineConfig({
  base: "/app/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
