import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/",
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  server: {
    port: 5173,
    proxy: {
      "/v1/capabilities": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/v1/knowledge-bases": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/v1/workflow": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
