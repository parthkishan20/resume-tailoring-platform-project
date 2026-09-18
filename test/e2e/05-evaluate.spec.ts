// test/e2e/05-evaluate.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import {
  MOCK_EVALUATION_SCORE,
  MOCK_MATCHED_KEYWORD,
  MOCK_MISSING_KEYWORD,
} from "../fixtures/mock-constants";
import { clearAllResumes, clickEvaluate, createResume, setMasterResume } from "./helpers";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");
const SAMPLE_JD = readFileSync(join(__dirname, "../fixtures/sample-jd.txt"), "utf-8");

test.describe("Evaluate", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
  });

  test("scores the master resume against a job description", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=inspector-tab-evaluate]").click();
    await page.locator("[data-testid=evaluate-job-description]").fill(SAMPLE_JD);
    await clickEvaluate(page);

    const result = page.locator("[data-testid=evaluate-result]");
    await expect(result).toBeVisible({ timeout: 30_000 });
    await expect(result).toContainText(`${MOCK_EVALUATION_SCORE}`);
    await expect(result).toContainText(MOCK_MATCHED_KEYWORD);
    await expect(result).toContainText(MOCK_MISSING_KEYWORD);
  });

  test("scores whichever generated resume is open in the Library", async ({
    page,
    request,
  }) => {
    await createResume(request, SAMPLE_JD);

    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await page.locator("[data-testid=resume-list-item]").first().click();

    await page.locator("[data-testid=inspector-tab-evaluate]").click();
    await page.locator("[data-testid=evaluate-job-description]").fill(SAMPLE_JD);
    await clickEvaluate(page);

    await expect(page.locator("[data-testid=evaluate-result]")).toBeVisible({ timeout: 30_000 });
  });

  test("the evaluate action stays disabled when the Library has nothing selected", async ({
    page,
  }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await page.locator("[data-testid=inspector-tab-evaluate]").click();
    await page.locator("[data-testid=evaluate-job-description]").fill(SAMPLE_JD);
    await expect(page.locator("[data-testid=evaluate-button]")).toBeDisabled();
    await expect(page.locator("[data-testid=evaluate-result]")).toHaveCount(0);
  });
});
