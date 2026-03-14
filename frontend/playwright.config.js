import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:18930",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
  ],
  webServer: {
    command: "cd .. && python3 tests/dashboard_fixture_server.py --port 18930 --frontend-dist frontend/dist",
    url: "http://127.0.0.1:18930/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
