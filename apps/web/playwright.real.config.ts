import { defineConfig, devices } from "@playwright/test";
import { testBasicAuth, testBasicAuthEnv } from "./tests/support/basic-auth";

const webURL = "http://127.0.0.1:3108";

export default defineConfig({
  testDir: "./tests/real-api",
  testMatch: "list.spec.ts",
  outputDir: "../../tmp/playwright/real-api-results",
  workers: 1,
  retries: 0,
  use: {
    ...devices["Desktop Chrome"],
    baseURL: webURL,
    httpCredentials: { ...testBasicAuth, origin: webURL },
    viewport: { width: 1280, height: 720 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "pnpm start --hostname 127.0.0.1 --port 3108",
    url: `${webURL}/health`,
    env: {
      ...testBasicAuthEnv,
      NODE_ENV: "production",
      NEXT_TELEMETRY_DISABLED: "1",
      PRESSWATCH_API_BASE_URL: "http://127.0.0.1:8001",
    },
    reuseExistingServer: false,
    timeout: 120000,
  },
});
