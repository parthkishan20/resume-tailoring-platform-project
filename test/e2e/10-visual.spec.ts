// test/e2e/10-visual.spec.ts
//
// Visual regression baselines (task 4.2, D-44's visual half). Playwright's
// own `toHaveScreenshot()` — see playwright.config.ts's `expect.toHaveScreenshot`
// for the tolerance and animation settings shared by every test here.
//
// Baselines were generated live against a real built image (see
// docs/reports/4-4.2.md for how) on darwin-arm64, chromium 125 (build
// v1117, the version @playwright/test 1.44.0 pins). Playwright's own visual
// comparisons are platform- and browser-build-specific: running this file
// on a different OS or a different pinned chromium build will need fresh
// baselines (`npx playwright test 10-visual.spec.ts --update-snapshots`),
// not a sign the UI regressed.
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import {
  clearAllResumes,
  createResume,
  setMasterResume,
  setTheme,
} from "./helpers";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");

test.describe("Visual: onboarding", () => {
  test.beforeEach(async ({ request }) => {
    await request.delete("/api/master-resume").catch(() => {});
  });

  test("empty state, light", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=empty-state]")).toBeVisible();
    await expect(page).toHaveScreenshot("onboarding-empty-state-light.png", { fullPage: true });
  });

  test("empty state, dark", async ({ page }) => {
    await setTheme(page, "dark");
    await page.goto("/");
    await expect(page.locator("[data-testid=empty-state]")).toBeVisible();
    await expect(page).toHaveScreenshot("onboarding-empty-state-dark.png", { fullPage: true });
  });

  // D-43: "responsive down to tablet." One baseline at a tablet width pins
  // that the onboarding two-column layout (actions + sample preview) does
  // not overflow or overlap there, the same way 06-library.spec.ts's widened
  // viewport documents a *known-broken* width rather than asserting a good
  // one — this is the inverse case, a width the app is expected to handle.
  test("empty state, tablet width", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto("/");
    await expect(page.locator("[data-testid=empty-state]")).toBeVisible();
    await expect(page).toHaveScreenshot("onboarding-empty-state-tablet.png", { fullPage: true });
  });
});

test.describe("Visual: master document", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
  });

  // Editor mode, not split or preview: the PDF preview pane renders through
  // Chromium's own PDF viewer, whose sub-pixel output is not guaranteed
  // stable across runs on the same machine, let alone across environments.
  // The editor's CodeMirror content is plain DOM and deterministic.
  test("editor mode, light", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=mode-editor]").click();
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible();
    await expect(page).toHaveScreenshot("master-document-editor-light.png", { fullPage: true });
  });

  test("editor mode, dark", async ({ page }) => {
    await setTheme(page, "dark");
    await page.goto("/");
    await page.locator("[data-testid=mode-editor]").click();
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible();
    // D-87 is fixed (YamlEditor.tsx now passes theme="none" to CodeMirror,
    // so the library's own bundled light theme no longer sits underneath
    // the token-driven one). The pre-fix baseline here documented the bug
    // itself (a white editor background in dark mode) and has been deleted
    // rather than kept as a now-wrong "known good" image; this assertion
    // will write a fresh baseline reflecting the fix the next time it runs
    // against a real browser, which is what confirms the fix visually.
    await expect(page).toHaveScreenshot("master-document-editor-dark.png", { fullPage: true });
  });

  test("editor mode, tablet width", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto("/");
    await page.locator("[data-testid=mode-editor]").click();
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible();
    await expect(page).toHaveScreenshot("master-document-editor-tablet.png", { fullPage: true });
  });
});

test.describe("Visual: Tailor", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
  });

  test("empty Tailor tab, light", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=inspector-tab-tailor]")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page).toHaveScreenshot("tailor-tab-light.png", { fullPage: true });
  });

  test("empty Tailor tab, dark", async ({ page }) => {
    await setTheme(page, "dark");
    await page.goto("/");
    await expect(page.locator("[data-testid=inspector-tab-tailor]")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page).toHaveScreenshot("tailor-tab-dark.png", { fullPage: true });
  });
});

test.describe("Visual: Library", () => {
  test.beforeEach(async ({ request }) => {
    test.setTimeout(60_000);
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
    await createResume(request, "Visual Corp — Engineer");
  });

  test("list view, light", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(1);
    await expect(page).toHaveScreenshot("library-list-light.png", {
      fullPage: true,
      // The row's created-at date (`toLocaleDateString()`) is today's real
      // date, not fixture data — masked so the baseline does not go stale
      // by the calendar.
      mask: [page.locator("[data-testid=resume-list-item] .font-lp-mono")],
    });
  });

  test("list view, dark", async ({ page }) => {
    await setTheme(page, "dark");
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(1);
    await expect(page).toHaveScreenshot("library-list-dark.png", {
      fullPage: true,
      mask: [page.locator("[data-testid=resume-list-item] .font-lp-mono")],
    });
  });

  test("list view, tablet width", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(1);
    await expect(page).toHaveScreenshot("library-list-tablet.png", {
      fullPage: true,
      mask: [page.locator("[data-testid=resume-list-item] .font-lp-mono")],
    });
  });

  test.describe("open document", () => {
    // Widened, exactly as 06-library.spec.ts's own "document" describe
    // block is, to get a usable baseline of the document itself rather
    // than a screenshot dominated by D-77's overlap (which has its own
    // dedicated baseline below, deliberately at the default width).
    test.use({ viewport: { width: 1600, height: 900 } });

    test("editor mode, light, at 1600x900", async ({ page }) => {
      await page.goto("/");
      await page.locator("[data-testid=nav-library]").click();
      await page.locator("[data-testid=resume-list-item]").first().click();
      await page.locator("[data-testid=mode-editor]").click();
      await expect(page.locator("[data-testid=resume-yaml-editor]")).toBeVisible();
      await expect(page).toHaveScreenshot("library-document-editor-light.png", {
        fullPage: true,
        mask: [page.locator("header .font-lp-mono")],
      });
    });
  });

  // D-77 is fixed (GeneratedResumeDocument.tsx's header now queries its own
  // `@container` width via `@xl:*` instead of the global `lg:` viewport
  // breakpoint, so it only goes single-row once its own column has room).
  // The pre-fix baseline here (`library-document-header-overlap-d77.png`)
  // documented the bug itself (the header's buttons overlapping the
  // Inspector's tab strip at the suite's real default viewport) and has been
  // deleted rather than kept as a now-wrong "known good" image; this
  // assertion will write a fresh baseline reflecting the fix (a two-row
  // header, since 364px of column width is still well under the @xl 576px
  // threshold) the next time it runs against a real browser, which is what
  // confirms the fix visually.
  test("open document header, no overlap, at the default viewport (D-77)", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-library]").click();
    await page.locator("[data-testid=resume-list-item]").first().click();
    await expect(page.locator("[data-testid=delete-resume-document]")).toBeAttached();
    await expect(page).toHaveScreenshot("library-document-header-fixed-d77.png", {
      fullPage: true,
      mask: [page.locator("header .font-lp-mono")],
    });
  });
});

test.describe("Visual: settings", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
  });

  test("appearance dialog, light", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=nav-appearance]").click();
    await expect(page.locator('[role="radiogroup"][aria-label="Theme"]')).toBeVisible();
    await expect(page).toHaveScreenshot("settings-appearance-light.png", { fullPage: true });
  });

  test("appearance dialog, dark", async ({ page }) => {
    await setTheme(page, "dark");
    await page.goto("/");
    await page.locator("[data-testid=nav-appearance]").click();
    await expect(page.locator('[role="radiogroup"][aria-label="Theme"]')).toBeVisible();
    await expect(page).toHaveScreenshot("settings-appearance-dark.png", { fullPage: true });
  });
});
