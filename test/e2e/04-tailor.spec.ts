// test/e2e/04-tailor.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import { MOCK_RESUME_NAME_FRAGMENT } from "../fixtures/mock-constants";
import { clearAllResumes, clickGenerate, setMasterResume } from "./helpers";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");
const SAMPLE_JD = readFileSync(join(__dirname, "../fixtures/sample-jd.txt"), "utf-8");

test.describe("Tailor", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
  });

  test("the generate button is disabled until a job description is entered", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=inspector-tab-tailor]")).toBeVisible();
    await expect(page.locator("[data-testid=generate-button]")).toBeDisabled();

    await page.locator("[data-testid=job-description]").fill(SAMPLE_JD);
    await expect(page.locator("[data-testid=generate-button]")).toBeEnabled();
  });

  test("tailoring a resume opens it in the Library and hands off to Evaluate", async ({
    page,
  }) => {
    await page.goto("/");
    await page.locator("[data-testid=job-description]").fill(SAMPLE_JD);
    await clickGenerate(page);

    await expect(page.locator("[data-testid=generated-resume-preview]")).toBeVisible({
      timeout: 30_000,
    });
    // The handoff switches the inspector to Evaluate automatically.
    await expect(page.locator("[data-testid=inspector-tab-evaluate]")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // The new resume is in the Library list beside the document.
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(1);
    await expect(page.locator("[data-testid=resume-name]").first()).toContainText(
      MOCK_RESUME_NAME_FRAGMENT,
    );
  });
});
