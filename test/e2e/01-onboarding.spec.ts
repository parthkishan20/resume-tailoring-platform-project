// test/e2e/01-onboarding.spec.ts
import { test, expect } from "@playwright/test";
import { resetChat, resetMasterResume } from "./helpers";

test.describe("Onboarding: first run", () => {
  test.beforeEach(async ({ request }) => {
    await resetMasterResume(request);
    await resetChat(request);
  });

  test("empty state renders with the guided first-run UI", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=empty-state]")).toBeVisible();
    await expect(page.locator("[data-testid=pdf-import-zone]")).toBeVisible();
    await expect(page.locator("[data-testid=onboarding-sample]")).toBeVisible();
    await expect(page.locator("[data-testid=onboarding-scratch]")).toBeVisible();
  });

  test("starting from the sample creates a master resume and opens the workspace", async ({
    page,
  }) => {
    await page.goto("/");
    await page.locator("[data-testid=onboarding-sample]").click();
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("[data-testid=nav-rail]")).toBeVisible();
  });

  test("writing from scratch creates an empty master resume and opens the workspace", async ({
    page,
  }) => {
    await page.goto("/");
    await page.locator("[data-testid=onboarding-scratch]").click();
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible({ timeout: 15_000 });
  });
});
