import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";
import { testBasicAuth, testBasicAuthEnv } from "./tests/support/basic-auth";
import { fixedClockFile, smokeClockFile } from "./tests/support/rate-limit-clock";

const devURL = "http://127.0.0.1:3105";
const productionURL = "http://127.0.0.1:3106";
const rateLimitURL = "http://127.0.0.1:3111";

const productionServerEnv = {
  NODE_ENV: "production",
  NEXT_TELEMETRY_DISABLED: "1",
  PRESSWATCH_API_BASE_URL: "http://127.0.0.1:3107",
};

const authenticatedProductionServerEnv = {
  ...productionServerEnv,
  ...testBasicAuthEnv,
  NODE_OPTIONS: `--require ${resolve("tests/support/server-clock.cjs")}`,
  PRESSWATCH_TEST_CLOCK_FILE: resolve("../../tmp/playwright/server-clock.json"),
};

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
      testMatch: [
        "production.spec.ts",
        "list.spec.ts",
        "search.spec.ts",
        "category.spec.ts",
        "url.spec.ts",
      ],
      use: {
        baseURL: productionURL,
        httpCredentials: { ...testBasicAuth, origin: productionURL },
      },
    },
    {
      name: "request-rate-limit",
      testMatch: "request-rate-limit.spec.ts",
      use: {
        baseURL: rateLimitURL,
        httpCredentials: { ...testBasicAuth, origin: rateLimitURL },
      },
    },
  ],
  webServer: [
    {
      command: "node tests/support/api-server.mjs",
      url: "http://127.0.0.1:3107/__ready",
      reuseExistingServer: false,
      timeout: 10_000,
    },
    {
      command: "pnpm dev --hostname 127.0.0.1 --port 3105",
      url: `${devURL}/third-party-notices.txt`,
      env: { NODE_ENV: "development", NEXT_TELEMETRY_DISABLED: "1" },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm start --hostname 127.0.0.1 --port 3106",
      url: `${productionURL}/health`,
      env: {
        ...authenticatedProductionServerEnv,
        PRESSWATCH_TEST_RATE_LIMIT_CLOCK_FILE: smokeClockFile,
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm start --hostname 127.0.0.1 --port 3111",
      url: `${rateLimitURL}/health`,
      env: {
        ...authenticatedProductionServerEnv,
        PRESSWATCH_TEST_RATE_LIMIT_CLOCK_FILE: fixedClockFile,
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm start --hostname 127.0.0.1 --port 3110",
      port: 3110,
      env: {
        ...productionServerEnv,
        PRESSWATCH_BASIC_AUTH_USER: testBasicAuth.username,
        PRESSWATCH_BASIC_AUTH_PASSWORD: "",
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
