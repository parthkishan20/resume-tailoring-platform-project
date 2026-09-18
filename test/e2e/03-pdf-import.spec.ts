// test/e2e/03-pdf-import.spec.ts
import { test, expect } from "@playwright/test";
import { resetMasterResume } from "./helpers";

test.describe("Onboarding: PDF import", () => {
  test.beforeEach(async ({ request }) => {
    await resetMasterResume(request);
  });

  test("importing a PDF creates the master resume from the extracted text", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=pdf-import-zone]")).toBeVisible();

    // Playwright cannot drive a native OS drag-and-drop; the zone's file
    // input stays in the tab order and accessibility tree (D-39), so
    // `setInputFiles` on it exercises the same `onChange` path a real drop or
    // a keyboard-driven file picker would.
    const minimalPdf = Buffer.from(
      "%PDF-1.4\n1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n" +
        "2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj\n" +
        "3 0 obj<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>endobj\n" +
        "xref\n0 4\n0000000000 65535 f\r\n0000000009 00000 n\r\n" +
        "0000000058 00000 n\r\n0000000115 00000 n\r\n" +
        "trailer<</Size 4 /Root 1 0 R>>\nstartxref\n190\n%%EOF",
    );

    await page.locator("[data-testid=pdf-import-zone] input[type=file]").setInputFiles({
      name: "resume.pdf",
      mimeType: "application/pdf",
      buffer: minimalPdf,
    });

    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible({ timeout: 15_000 });
  });
});
