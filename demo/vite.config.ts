import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE ?? "/",
  server: {
    port: 5173,
    proxy: {
      "/v1/workflow": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
