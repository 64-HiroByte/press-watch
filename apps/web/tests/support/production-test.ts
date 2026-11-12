import { test as base } from "@playwright/test";
import { refillSmokeBucket } from "./rate-limit-clock";

export { expect, type Page } from "@playwright/test";

export const test = base.extend<{ refillRateLimit: void }>({
  refillRateLimit: [
    // oxlint-disable-next-line eslint/no-empty-pattern -- Playwrightのfixtureは第1引数の分割代入が必要。
    async ({}, use) => {
      await refillSmokeBucket();
      await use();
    },
    { auto: true },
  ],
});
