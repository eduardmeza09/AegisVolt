import { defineConfig } from "@playwright/test";

// E2E de navegador contra un stack levantado (docker compose --profile app => http://localhost:8081/web/,
// o el frontend_url de un ambiente desplegado). En Windows se puede usar Edge: PW_CHANNEL=msedge.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8081/web/",
    channel: process.env.PW_CHANNEL || undefined,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
