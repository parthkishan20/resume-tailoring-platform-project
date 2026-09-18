// test/e2e/08-settings.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import { clearAllResumes, clickGenerate, resetRules, setMasterResume } from "./helpers";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");
const SAMPLE_JD = readFileSync(join(__dirname, "../fixtures/sample-jd.txt"), "utf-8");

test.describe("Settings: generation rules", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
    await resetRules(request);
  });

  test("the rules dialog opens, edits a value and saves", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-rules]").click();

    const form = page.locator("[data-testid=rules-form]");
    await expect(form).toBeVisible();

    const firstInput = form.locator("input").first();
    await firstInput.fill("3");

    await page.locator("[data-testid=rules-save]").click();
    await expect(form).toBeHidden({ timeout: 15_000 });
  });

  test("generation still works after a rule change", async ({ page, request }) => {
    test.setTimeout(60_000);
    await clearAllResumes(request);
    await request.put("/api/rules", {
      data: { rules: [{ section: "experience", rule_key: "max_bullets", rule_value: "1" }] },
    });

    await page.goto("/");
    await page.locator("[data-testid=job-description]").fill(SAMPLE_JD);
    await clickGenerate(page);
    await expect(page.locator("[data-testid=generated-resume-preview]")).toBeVisible({
      timeout: 30_000,
    });
  });
});

test.describe("Settings: assistant prompt", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
    await request.delete("/api/system-prompt").catch(() => {});
  });

  test("the assistant prompt dialog opens, edits and saves", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-prompt]").click();

    const prompt = page.locator("[data-testid=assistant-prompt]");
    await expect(prompt).toBeVisible();
    await prompt.fill("Custom standing instructions from the e2e suite.");

    await page.locator("[data-testid=assistant-prompt-save]").click();
    await expect(prompt).toBeHidden({ timeout: 15_000 });
  });
});

test.describe("Settings: appearance", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
  });

  test("switching to dark applies the token swap", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-appearance]").click();

    await page.locator("[data-testid=theme-dark]").click();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-theme")))
      .toBe("dark");

    await page.locator("[data-testid=theme-light]").click();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-theme")))
      .toBe("light");
  });
});
