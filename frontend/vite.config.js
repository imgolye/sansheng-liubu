import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = process.env.MISSION_CONTROL_API_TARGET || "http://127.0.0.1:18890";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return;
          }

          if (
            id.includes("/react/") ||
            id.includes("/react-dom/") ||
            id.includes("/react-router-dom/")
          ) {
            return "react";
          }

          if (id.includes("/@ant-design/icons/")) {
            return;
          }
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target,
        changeOrigin: true,
      },
      "/events": {
        target,
        changeOrigin: true,
      },
      "/login": {
        target,
        changeOrigin: true,
      },
      "/logout": {
        target,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
  },
});
