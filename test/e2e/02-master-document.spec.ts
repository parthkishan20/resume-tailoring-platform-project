// test/e2e/02-master-document.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import { confirmAlertDialog, setMasterResume } from "./helpers";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");

test.describe("Master document: view, edit, save, delete", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
  });

  test("loads the stored YAML and the preview", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible();
    await expect(page.locator("[data-testid=save-master-resume]")).toBeDisabled();

    await page.locator("[data-testid=mode-preview]").click();
    await expect(page.locator("[data-testid=resume-preview]")).toBeVisible({ timeout: 15_000 });

    await page.locator("[data-testid=mode-split]").click();
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible();
    await expect(page.locator("[data-testid=resume-preview]")).toBeVisible();
  });

  test("editing marks the document dirty and saving clears it", async ({ page }) => {
    await page.goto("/");
    // Retypes exactly the second line (`  name: Mock User`), replacing it
    // with a single-line edit. Never pressing Enter mid-edit sidesteps
    // CodeMirror's auto-indent-on-newline, which would otherwise fight with
    // typing a pre-indented multi-line replacement.
    const editor = page.locator("[data-testid=yaml-editor] .cm-content");
    await editor.click();
    await page.keyboard.press("ControlOrMeta+Home");
    await page.keyboard.press("ArrowDown");
    // Two Home presses: CodeMirror's "smart home" lands on the first
    // non-whitespace character first, and only a second press reaches true
    // column 0 — one press alone leaves the line's original indentation in
    // place, so a replacement that includes its own leading spaces doubles
    // up on indentation instead of replacing it.
    await page.keyboard.press("Home");
    await page.keyboard.press("Home");
    await page.keyboard.press("Shift+End");
    await page.keyboard.type("  name: Mock User Edited");

    const saveButton = page.locator("[data-testid=save-master-resume]");
    await expect(saveButton).toBeEnabled();

    await saveButton.click();
    await expect(saveButton).toBeDisabled({ timeout: 15_000 });
  });

  test("deleting the master resume returns to onboarding", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=delete-master-resume]").click();
    await confirmAlertDialog(page);
    await expect(page.locator("[data-testid=empty-state]")).toBeVisible({ timeout: 15_000 });
  });
});
