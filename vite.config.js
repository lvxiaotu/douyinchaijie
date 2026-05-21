import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8010";
  return {
    plugins: [tailwindcss(), react()],
    test: {
      environment: "jsdom",
      globals: true,
    },
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": apiProxyTarget,
      },
    },
  };
});
