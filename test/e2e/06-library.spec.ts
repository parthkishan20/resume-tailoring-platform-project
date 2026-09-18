// test/e2e/06-library.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import {
  clearAllResumes,
  confirmAlertDialog,
  createResume,
  setMasterResume,
  submitRenameDialog,
} from "./helpers";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");
// SAMPLE_YAML's phone ("+10000000000") fails resume_schema.validate's real
// phonenumbers check — fine for PUT /api/master-resume (D-08's lenient
// normalize prunes it) but not for a strict-validated PATCH. Used only where
// this file calls a strict-validated write directly.
const VALID_PHONE_YAML = SAMPLE_YAML.replace('"+10000000000"', '"+14155552671"');

test.describe("Library: sort and list", () => {
  test.beforeEach(async ({ request }) => {
    test.setTimeout(120_000);
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
    await createResume(request, "Alpha Corp — Engineer");
    await createResume(request, "Beta Corp — Engineer");
  });

  test("sort by date and by job description both render the two rows", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();

    await expect(page.locator("[data-testid=sort-date]")).toBeVisible();
    await expect(page.locator("[data-testid=sort-jd]")).toBeVisible();

    await page.locator("[data-testid=sort-jd]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(2);

    await page.locator("[data-testid=sort-order-toggle]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(2);

    await page.locator("[data-testid=sort-date]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(2);
  });
});

test.describe("Library: pagination", () => {
  test.beforeEach(async ({ request }) => {
    test.setTimeout(240_000);
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
    // The default page size is 20 (resumes.py's `limit` default); 22 rows
    // forces a real second page rather than exercising a control that always
    // renders null because `ResumePagination` hides itself at one page.
    for (let i = 0; i < 22; i += 1) {
      await createResume(request, `Pagination Corp ${i} — Engineer`);
    }
  });

  test("paging forward and back changes the visible rows", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();

    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(20);
    await expect(page.locator("[data-testid=library-page-prev]")).toBeDisabled();
    await expect(page.locator("[data-testid=library-page-next]")).toBeEnabled();

    await page.locator("[data-testid=library-page-next]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(2);
    await expect(page.locator("[data-testid=library-page-next]")).toBeDisabled();

    await page.locator("[data-testid=library-page-prev]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(20);
  });
});

test.describe("Library: document (rename, edit, re-render, delete)", () => {
  // Wider than the suite default. At the standard 1280x720 "Desktop Chrome"
  // viewport, the nav (216px) + list column (320px) + inspector (380px)
  // leave GeneratedResumeDocument's own column only ~364px, and its header
  // (rename, Save, Re-render, Delete, ModeSwitch) commits to a single row at
  // the *global* `lg` breakpoint regardless of that column's actual width —
  // so the actions visually overlap the Inspector's tab strip and become
  // unclickable. A real, reproduced defect (docs/reports/4-4.1.md); widening
  // the viewport here tests this describe's actual subject (the document's
  // behaviour) instead of re-proving a layout bug already on file.
  test.use({ viewport: { width: 1600, height: 900 } });

  test.beforeEach(async ({ request }) => {
    test.setTimeout(60_000);
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
    await createResume(request, "Gamma Corp — Engineer");
  });

  test("renaming from the list row updates the name shown there", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await page.locator("[data-testid=rename-resume]").click();

    const input = page.locator("[data-testid=rename-input]");
    await input.fill("Renamed from the list");
    // A click, not Enter: see submitRenameDialog's doc comment for why Enter
    // is unreliable here specifically (ResumeListRow's own keydown handler).
    await submitRenameDialog(page);

    await expect(page.locator("[data-testid=resume-name]").first()).toContainText(
      "Renamed from the list",
    );
  });

  test("renaming from the open document updates its header", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await page.locator("[data-testid=resume-list-item]").first().click();

    await page.locator("[data-testid=rename-open-resume]").click();
    const input = page.locator("[data-testid=rename-input]");
    await input.fill("Renamed from the document");
    await submitRenameDialog(page);

    await expect(page.locator("[data-testid=resume-name]").first()).toContainText(
      "Renamed from the document",
    );
  });

  test("editing the YAML and saving, then re-rendering, keeps the document open", async ({
    page,
    request,
  }) => {
    // The stored yaml_content this describe's beforeEach just generated is
    // not usable as an edit starting point: under LLM_MOCK, the two-pass
    // pipeline's audit stub (llm/stub.py's `"ResumeAuditor" in system`
    // branch) locates the candidate CV with `user_content.find("cv:")` and
    // returns everything from there to the end of the *whole audit prompt*,
    // which also contains a trailing "Master:" (the full master resume) and
    // "JD:" (the raw job description) section appended after the candidate
    // CV for the auditor's context. So every generated resume's stored YAML
    // is genuinely invalid (multiple top-level "cv:" blocks) — confirmed via
    // `GET /api/resumes/{id}` directly, not an artifact of this test. Logged
    // in docs/reports/4-4.1.md; `llm/stub.py` is `llm`'s, not this task's.
    // Seeding a known-valid document first (mirroring `setMasterResume`)
    // tests the real subject here — editing and saving through the UI — on
    // top of the document the product should have stored in the first place.
    const list = await request.get("/api/resumes", { params: { limit: 1 } });
    const { items } = (await list.json()) as { items: Array<{ id: number }> };
    const seeded = await request.patch(`/api/resumes/${items[0].id}`, {
      data: { yaml_content: VALID_PHONE_YAML },
    });
    if (!seeded.ok()) throw new Error(`Seed PATCH failed: ${seeded.status()}`);

    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await page.locator("[data-testid=resume-list-item]").first().click();

    await expect(page.locator("[data-testid=resume-yaml-editor]")).toBeVisible();
    // A single-line retype of line 2 (`  name: Mock User`), never pressing
    // Enter, so CodeMirror's auto-indent-on-newline cannot fight a
    // pre-indented multi-line paste (as in 02-master-document.spec.ts).
    const editor = page.locator("[data-testid=resume-yaml-editor] .cm-content");
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

    const saveButton = page.locator("[data-testid=save-resume]");
    await expect(saveButton).toBeEnabled();
    await saveButton.click();
    await expect(saveButton).toBeDisabled({ timeout: 15_000 });

    await page.locator("[data-testid=render-resume]").click();
    await expect(page.locator("[data-testid=generated-resume-preview]")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("deleting a resume from the list removes it", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(1);

    await page.locator("[data-testid=delete-resume]").click();
    await confirmAlertDialog(page);

    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(0, {
      timeout: 15_000,
    });
  });

  test("deleting the open document from its header removes it", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await page.locator("[data-testid=resume-list-item]").first().click();

    await page.locator("[data-testid=delete-resume-document]").click();
    await confirmAlertDialog(page);

    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(0, {
      timeout: 15_000,
    });
  });
});
