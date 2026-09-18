// test/e2e/06-resume-list-sort.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");

/** Shape of GET /api/resumes (backend/app/database.py list_resumes). */
interface ResumeListPage {
  items: Array<{ id: number }>;
  total: number;
}

test.describe("Scenario 6: Resume list sort", () => {
  test.beforeEach(async ({ request }) => {
    // This spec generates its own resumes rather than reading whatever the
    // last run left behind, so it needs more than the default 30s budget.
    test.setTimeout(120_000);

    await request.put("/api/master-resume", { data: { yaml_content: SAMPLE_YAML } });

    // Start from an empty list so the items asserted below are the ones this
    // spec created, never rows left behind by an earlier run.
    const existing = await request.get("/api/resumes", { params: { limit: 100 } });
    expect(existing.ok()).toBeTruthy();
    const existingPage = (await existing.json()) as ResumeListPage;
    for (const row of existingPage.items) {
      const deleted = await request.delete(`/api/resumes/${row.id}`);
      expect(deleted.ok()).toBeTruthy();
    }

    // Create the two resumes this spec sorts. /api/resumes/stream is SSE: the
    // response headers arrive before the work is done, so read the whole body
    // and assert the terminal `done` event. Awaiting the text is what makes the
    // row exist before the assertions run.
    for (const jobDescription of ["Alpha Corp — Engineer", "Beta Corp — Engineer"]) {
      const response = await request.post("/api/resumes/stream", {
        data: { job_description: jobDescription },
        timeout: 60_000,
      });
      expect(response.ok()).toBeTruthy();
      const body = await response.text();
      expect(body).toContain("event: done");
      expect(body).not.toContain("event: error");
    }

    const created = await request.get("/api/resumes", { params: { limit: 100 } });
    expect(created.ok()).toBeTruthy();
    expect(((await created.json()) as ResumeListPage).total).toBe(2);
  });

  test("sort by date and by JD buttons work", async ({ page }) => {
    await page.goto("/");
    // Navigate to history tab
    await page.getByText("Resumes").click();
    // Sort controls visible
    await expect(page.locator("[data-testid=sort-date]")).toBeVisible();
    await expect(page.locator("[data-testid=sort-jd]")).toBeVisible();
    // Click sort by JD
    await page.locator("[data-testid=sort-jd]").click();
    // List container still visible
    await expect(page.locator("[data-testid=resume-list]")).toBeVisible();
    // List items rendered — both of the resumes created in beforeEach
    await expect(page.locator("[data-testid=resume-list-item]").first()).toBeVisible();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(2);
    // Click back to date sort
    await page.locator("[data-testid=sort-date]").click();
    await expect(page.locator("[data-testid=resume-list]")).toBeVisible();
    // List items rendered after re-sort
    await expect(page.locator("[data-testid=resume-list-item]").first()).toBeVisible();
    await expect(page.locator("[data-testid=resume-list-item]")).toHaveCount(2);
  });
});
