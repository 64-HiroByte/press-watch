import { defineConfig, devices } from "@playwright/test";

const devURL = "http://127.0.0.1:3105";
const productionURL = "http://127.0.0.1:3106";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "../../tmp/playwright/test-results",
  forbidOnly: !!process.env.CI,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 720 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "dev-mock",
      testMatch: "mock.spec.ts",
      use: { baseURL: devURL },
    },
    {
      name: "production-smoke",
      testMatch: "production.spec.ts",
      use: { baseURL: productionURL },
    },
  ],
  webServer: [
    {
      command: "pnpm dev --hostname 127.0.0.1 --port 3105",
      url: devURL,
      env: { NODE_ENV: "development", NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm start --hostname 127.0.0.1 --port 3106",
      url: productionURL,
      env: { NODE_ENV: "production", NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
