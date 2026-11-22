import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// base "./": los assets se resuelven relativos a /<stage>/_user_request_/web/ del API Gateway.
// En desarrollo, /graphql se reenvía al gateway (docker compose: http://localhost:8080
// o la URL del API Gateway de un ambiente vía VITE_DEV_PROXY_TARGET).
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/graphql": {
        target: process.env.VITE_DEV_PROXY_TARGET ?? "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  test: { environment: "node" },
});
