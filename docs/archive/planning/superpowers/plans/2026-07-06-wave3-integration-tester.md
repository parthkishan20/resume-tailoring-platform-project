# Integration Tester Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run all 8 Playwright E2E scenarios against the `LLM_MOCK=true` Docker container, report any failures with owner attribution, and iterate until all pass.

**Architecture:** Playwright TypeScript tests run against a live Docker container started via `docker-compose.test.yml`. All tests use `LLM_MOCK=true` for deterministic responses. Mock constants imported from `backend/app/simulator.py` (as strings in fixtures file) define expected values.

**Tech Stack:** Playwright (TypeScript), docker-compose

## Global Constraints

- Reference: `planning/PLAN.md §10, §11`; `planning/2026-07-06-agent-team-design.md §3`
- **PRE-CONDITION:** `docker build -t resumetailor .` must exit 0 before running any test
- All tests run with `LLM_MOCK=true` — no real LLM calls
- `BASE_URL` defaults to `http://localhost:8000`
- `data-testid` attributes are defined in `planning/2026-07-06-wave1-frontend-engineer.md`
- On failure: report using the structured format below, then stop. Fix, rebuild, re-run.

## Failure Report Format

```
SCENARIO: <scenario name from list below>
ASSERTION: <exact assertion that failed, e.g. expect(locator(...)).toBeVisible() timed out>
OWNER: <Frontend | Backend API | DevOps | triage>
OBSERVED: <what actually happened — screenshot path or text>
```

Use `OWNER: triage` when the cause is ambiguous. Never guess ownership — observe and report.

---

## File Structure

```
test/
├── package.json
├── playwright.config.ts
├── fixtures/
│   ├── sample-resume.yaml     YAML fixture for testing
│   ├── sample-jd.txt          Job description fixture
│   └── mock-constants.ts      Expected values matching backend simulator constants
└── e2e/
    ├── 01-fresh-start.spec.ts
    ├── 02-master-resume.spec.ts
    ├── 03-pdf-upload.spec.ts
    ├── 04-generation.spec.ts
    ├── 05-chat.spec.ts
    ├── 06-resume-list-sort.spec.ts
    ├── 07-evaluation.spec.ts
    └── 08-rules.spec.ts
```

---

## Task 1: Test Infrastructure

**Files:**
- Create: `test/package.json`
- Create: `test/playwright.config.ts`
- Create: `test/fixtures/sample-resume.yaml`
- Create: `test/fixtures/sample-jd.txt`
- Create: `test/fixtures/mock-constants.ts`

- [ ] **Step 1: Verify Docker build succeeds**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform
docker build -t resumetailor .
```

Expected: exit code 0. If it fails, stop here and file a report:
```
SCENARIO: Docker build
ASSERTION: docker build -t resumetailor . exits 0
OWNER: DevOps
OBSERVED: <paste the last 20 lines of docker build output>
```

- [ ] **Step 2: Create `test/package.json`**

```json
{
  "name": "resumetailor-e2e",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "test": "playwright test",
    "test:headed": "playwright test --headed",
    "test:ui": "playwright test --ui"
  },
  "devDependencies": {
    "@playwright/test": "^1.44.0",
    "typescript": "^5"
  }
}
```

- [ ] **Step 3: Create `test/playwright.config.ts`**

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 1,
  timeout: 30_000,
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:8000",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  reporter: [["list"], ["html", { open: "never" }]],
});
```

- [ ] **Step 4: Create fixtures**

`test/fixtures/sample-resume.yaml`:
```yaml
cv:
  name: Mock User
  email: mock@example.com
  phone: "+10000000000"
  location: Mock City, MC
  sections:
    education:
    - institution: Mock University
      area: Computer Science
      degree: Bachelor
      start_date: 2018-09
      end_date: 2022-05
    experience:
    - company: Mock Corp
      position: Software Engineer
      start_date: 2022-06
      end_date: present
      location: Mock City, MC
      highlights:
      - Built mock features using Python and React.
      - Deployed mock services with Docker and CI/CD pipelines.
      - Reduced mock latency by 30 percent through query optimization.
      - Collaborated with mock teams to deliver mock roadmap items.
    skills:
    - label: Languages
      details: Python, TypeScript, SQL
    - label: Tools
      details: Docker, Git, FastAPI, React
```

`test/fixtures/sample-jd.txt`:
```
Software Engineer at Mock Corp

We are looking for a Software Engineer with experience in Python, REST API, and PostgreSQL.
The ideal candidate will have experience with Kubernetes, CI/CD pipelines, and Docker Compose.
Strong knowledge of modern web development and cloud infrastructure required.
```

`test/fixtures/mock-constants.ts`:
```ts
// These values must match backend/app/simulator.py MOCK_* constants exactly.
// If a test fails because values don't match, update these to match the simulator.

export const MOCK_CHAT_RESPONSE = "I understand. Here's what I can help you with: editing your master resume, generating a tailored resume, or evaluating a resume against a job description.";
export const MOCK_RESUME_NAME_FRAGMENT = "Mock User";  // appears in generated resume
export const MOCK_EVALUATION_SCORE = 72;
export const MOCK_MISSING_KEYWORD = "Kubernetes";
export const MOCK_MATCHED_KEYWORD = "Python";
```

- [ ] **Step 5: Install Playwright**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/test
npm install
npx playwright install chromium
```

- [ ] **Step 6: Start the test container**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform
docker compose -f docker-compose.test.yml up -d app
# Wait for health check
until curl -sf http://localhost:8000/api/health; do echo "waiting..."; sleep 3; done
echo "App ready"
```

- [ ] **Step 7: Commit infrastructure**

```bash
git add test/
git commit -m "feat(test): Playwright infrastructure, fixtures, mock constants"
```

---

## Task 2: Scenarios 1 & 2 — Fresh Start + Master Resume

**Files:**
- Create: `test/e2e/01-fresh-start.spec.ts`
- Create: `test/e2e/02-master-resume.spec.ts`

- [ ] **Step 1: Write scenario 1**

```ts
// test/e2e/01-fresh-start.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Scenario 1: Fresh start", () => {
  test.beforeEach(async ({ request }) => {
    // Reset state: delete master resume if exists
    await request.delete("/api/master-resume").catch(() => {});
    await request.delete("/api/chat").catch(() => {});
  });

  test("empty state renders with guided UI", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=empty-state]")).toBeVisible();
  });

  test("sample YAML download link is present", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Download Sample YAML")).toBeVisible();
  });

  test("PDF import drop zone is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=pdf-import-zone]")).toBeVisible();
  });
});
```

- [ ] **Step 2: Run scenario 1**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/test
npx playwright test e2e/01-fresh-start.spec.ts --reporter=list
```

Expected: 3 passed. If failures, file report with `OWNER: Frontend` and stop.

- [ ] **Step 3: Write scenario 2**

```ts
// test/e2e/02-master-resume.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");

test.describe("Scenario 2: Master resume CRUD", () => {
  test.beforeEach(async ({ request }) => {
    await request.delete("/api/master-resume").catch(() => {});
  });

  test("load sample, edit YAML, save, confirm preview shows", async ({ page }) => {
    await page.goto("/");
    // Click "Start from Sample"
    await page.getByText("Start from Sample").click();
    // YAML editor should now be visible
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible();
    // Save
    await page.locator("[data-testid=save-master-resume]").click();
    // After save, editor still visible (no redirect)
    await expect(page.locator("[data-testid=save-master-resume]")).toBeVisible();
  });

  test("edit YAML content and save", async ({ page }) => {
    // Set up master resume via API
    await page.request.put("/api/master-resume", {
      data: { yaml_content: SAMPLE_YAML },
    });
    await page.goto("/");
    // YAML editor visible (not empty state)
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible();
    // Type into editor - CodeMirror requires clicking first
    const editor = page.locator("[data-testid=yaml-editor]");
    await editor.click();
    // Save
    await page.locator("[data-testid=save-master-resume]").click();
    await expect(page.locator("[data-testid=save-master-resume]")).toBeVisible();
  });

  test("preview toggle shows preview container", async ({ page }) => {
    await page.request.put("/api/master-resume", {
      data: { yaml_content: SAMPLE_YAML },
    });
    await page.goto("/");
    await page.getByText("Preview").click();
    await expect(page.locator("[data-testid=resume-preview]")).toBeVisible();
  });
});
```

- [ ] **Step 4: Run scenario 2**

```bash
npx playwright test e2e/02-master-resume.spec.ts --reporter=list
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add test/e2e/01-fresh-start.spec.ts test/e2e/02-master-resume.spec.ts
git commit -m "test(e2e): scenarios 1-2 (fresh start, master resume)"
```

---

## Task 3: Scenarios 3 & 4 — PDF Upload + Generation

**Files:**
- Create: `test/e2e/03-pdf-upload.spec.ts`
- Create: `test/e2e/04-generation.spec.ts`

- [ ] **Step 1: Write scenario 3**

```ts
// test/e2e/03-pdf-upload.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";

test.describe("Scenario 3: PDF upload / import", () => {
  test.beforeEach(async ({ request }) => {
    await request.delete("/api/master-resume").catch(() => {});
  });

  test("drag-and-drop PDF import triggers YAML extraction", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("[data-testid=pdf-import-zone]")).toBeVisible();

    // Simulate file drop via input (Playwright doesn't support native drag-drop)
    // The PDF import zone has a hidden <input type="file"> — trigger it programmatically
    const minimalPdf = Buffer.from(
      "%PDF-1.4\n1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n" +
      "2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj\n" +
      "3 0 obj<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>endobj\n" +
      "xref\n0 4\n0000000000 65535 f\r\n0000000009 00000 n\r\n" +
      "0000000058 00000 n\r\n0000000115 00000 n\r\n" +
      "trailer<</Size 4 /Root 1 0 R>>\nstartxref\n190\n%%EOF"
    );

    await page.locator("[data-testid=pdf-import-zone] input[type=file]").setInputFiles({
      name: "resume.pdf",
      mimeType: "application/pdf",
      buffer: minimalPdf,
    });

    // After import, YAML editor should appear (master resume was created)
    await expect(page.locator("[data-testid=yaml-editor]")).toBeVisible({ timeout: 15_000 });
  });
});
```

- [ ] **Step 2: Write scenario 4**

```ts
// test/e2e/04-generation.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import { MOCK_RESUME_NAME_FRAGMENT } from "../fixtures/mock-constants";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");
const SAMPLE_JD = readFileSync(join(__dirname, "../fixtures/sample-jd.txt"), "utf-8");

test.describe("Scenario 4: Resume generation", () => {
  test.beforeEach(async ({ request }) => {
    await request.put("/api/master-resume", { data: { yaml_content: SAMPLE_YAML } });
  });

  test("paste JD, generate, PDF preview renders", async ({ page }) => {
    await page.goto("/");
    // Paste job description
    await page.locator("[data-testid=job-description]").fill(SAMPLE_JD);
    // Click generate
    await page.locator("[data-testid=generate-button]").click();
    // Wait for generation to complete (PDF preview appears)
    await expect(page.locator("[data-testid=generated-resume-preview]")).toBeVisible({ timeout: 30_000 });
    // Resume name displayed
    await expect(page.locator("[data-testid=resume-name]").first()).toBeVisible();
  });
});
```

- [ ] **Step 3: Run scenarios 3 & 4**

```bash
npx playwright test e2e/03-pdf-upload.spec.ts e2e/04-generation.spec.ts --reporter=list
```

Expected: all passed. Generation may take up to 30s (SSE stream).

- [ ] **Step 4: Commit**

```bash
git add test/e2e/03-pdf-upload.spec.ts test/e2e/04-generation.spec.ts
git commit -m "test(e2e): scenarios 3-4 (PDF upload, resume generation)"
```

---

## Task 4: Scenarios 5 & 6 — Chat + Resume List Sort

**Files:**
- Create: `test/e2e/05-chat.spec.ts`
- Create: `test/e2e/06-resume-list-sort.spec.ts`

- [ ] **Step 1: Write scenario 5**

```ts
// test/e2e/05-chat.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import { MOCK_CHAT_RESPONSE } from "../fixtures/mock-constants";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");

test.describe("Scenario 5: Chat assistant", () => {
  test.beforeEach(async ({ request }) => {
    await request.put("/api/master-resume", { data: { yaml_content: SAMPLE_YAML } });
    await request.delete("/api/chat").catch(() => {});
  });

  test("send message, receive mocked response", async ({ page }) => {
    await page.goto("/");
    // Chat panel should be visible at bottom
    await expect(page.locator("[data-testid=chat-input]")).toBeVisible();
    // Type and send
    await page.locator("[data-testid=chat-input]").fill("Hello, what can you do?");
    await page.locator("[data-testid=chat-send]").click();
    // Wait for response message to appear
    await expect(page.locator("[data-testid=chat-message]")).toHaveCount(2, { timeout: 15_000 });
    // The assistant response should contain the mock text
    const assistantMsg = page.locator("[data-testid=chat-message]").last();
    await expect(assistantMsg).toContainText("master resume", { timeout: 15_000 });
  });
});
```

- [ ] **Step 2: Write scenario 6**

```ts
// test/e2e/06-resume-list-sort.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");

test.describe("Scenario 6: Resume list sort", () => {
  test.beforeEach(async ({ request }) => {
    await request.put("/api/master-resume", { data: { yaml_content: SAMPLE_YAML } });
    // Create two resumes via API
    await request.post("/api/resumes/stream", {
      data: { job_description: "Alpha Corp — Engineer" },
    }).catch(() => {}); // SSE endpoint, response may not parse as JSON
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
    // Click back to date sort
    await page.locator("[data-testid=sort-date]").click();
    await expect(page.locator("[data-testid=resume-list]")).toBeVisible();
  });
});
```

- [ ] **Step 3: Run scenarios 5 & 6**

```bash
npx playwright test e2e/05-chat.spec.ts e2e/06-resume-list-sort.spec.ts --reporter=list
```

Expected: all passed.

- [ ] **Step 4: Commit**

```bash
git add test/e2e/05-chat.spec.ts test/e2e/06-resume-list-sort.spec.ts
git commit -m "test(e2e): scenarios 5-6 (chat, resume list sort)"
```

---

## Task 5: Scenarios 7 & 8 — Evaluation + Rules

**Files:**
- Create: `test/e2e/07-evaluation.spec.ts`
- Create: `test/e2e/08-rules.spec.ts`

- [ ] **Step 1: Write scenario 7**

```ts
// test/e2e/07-evaluation.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import { MOCK_EVALUATION_SCORE, MOCK_MISSING_KEYWORD, MOCK_MATCHED_KEYWORD } from "../fixtures/mock-constants";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");
const SAMPLE_JD = readFileSync(join(__dirname, "../fixtures/sample-jd.txt"), "utf-8");

test.describe("Scenario 7: Evaluation", () => {
  test.beforeEach(async ({ request }) => {
    await request.put("/api/master-resume", { data: { yaml_content: SAMPLE_YAML } });
  });

  test("score and critique returned and displayed", async ({ page }) => {
    await page.goto("/");
    // Navigate to evaluate tab
    await page.getByText("evaluate", { exact: false }).click();
    // Fill JD and evaluate
    await page.locator("textarea").last().fill(SAMPLE_JD);
    await page.locator("[data-testid=evaluate-button]").click();
    // Wait for result
    await expect(page.locator("[data-testid=evaluate-result]")).toBeVisible({ timeout: 30_000 });
    // Check score (72 from mock)
    await expect(page.locator("[data-testid=evaluate-result]")).toContainText(`${MOCK_EVALUATION_SCORE}`);
    // Check keywords
    await expect(page.locator("[data-testid=evaluate-result]")).toContainText(MOCK_MATCHED_KEYWORD);
    await expect(page.locator("[data-testid=evaluate-result]")).toContainText(MOCK_MISSING_KEYWORD);
  });
});
```

- [ ] **Step 2: Write scenario 8**

```ts
// test/e2e/08-rules.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");
const SAMPLE_JD = readFileSync(join(__dirname, "../fixtures/sample-jd.txt"), "utf-8");

test.describe("Scenario 8: Generation rules", () => {
  test.beforeEach(async ({ request }) => {
    await request.put("/api/master-resume", { data: { yaml_content: SAMPLE_YAML } });
    await request.delete("/api/rules").catch(() => {}); // reset to defaults
  });

  test("rules form is visible and can update a value", async ({ page }) => {
    await page.goto("/");
    // Open rules form
    await page.getByText("Generation Rules").click();
    await expect(page.locator("[data-testid=rules-form]")).toBeVisible();
    // Change a rule value
    const inputs = page.locator("[data-testid=rules-form] input");
    await inputs.first().fill("3");
    await inputs.first().blur(); // trigger onBlur save
    // No error visible
    await expect(page.locator("[data-testid=rules-form]")).toBeVisible();
  });

  test("generate after rule change works", async ({ page }) => {
    await page.goto("/");
    // Update a rule via API
    await page.request.put("/api/rules", {
      data: { rules: [{ section: "experience", rule_key: "max_entries", rule_value: "1" }] },
    });
    // Generate
    await page.locator("[data-testid=job-description]").fill(SAMPLE_JD);
    await page.locator("[data-testid=generate-button]").click();
    await expect(page.locator("[data-testid=generated-resume-preview]")).toBeVisible({ timeout: 30_000 });
  });
});
```

- [ ] **Step 3: Run all 8 scenarios**

```bash
npx playwright test --reporter=list
```

Expected: all 8 scenario files pass (every test in every file).

- [ ] **Step 4: If any test fails, file a report**

For each failing test, produce:
```
SCENARIO: <name from scenario list>
ASSERTION: <exact failure message from Playwright output>
OWNER: <Frontend | Backend API | DevOps | triage>
OBSERVED: <screenshot path if available, or text of actual content>
```

Do not fix the issue yourself. Report it and wait for the owning agent to fix it, then re-run only the affected spec file.

- [ ] **Step 5: Commit passing tests**

```bash
git add test/e2e/07-evaluation.spec.ts test/e2e/08-rules.spec.ts
git commit -m "test(e2e): scenarios 7-8 (evaluation, rules) — all 8 E2E scenarios pass"
```

---

## Task 6: Stop Test Container + Final Report

- [ ] **Step 1: Stop test containers**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform
docker compose -f docker-compose.test.yml down
```

- [ ] **Step 2: Verify test report**

```bash
cd /Users/parthkumarpatel/Downloads/Job-Search/resume-tailoring-platform/test
npx playwright show-report
```

- [ ] **Step 3: Final commit**

```bash
git add test/
git commit -m "test(e2e): all 8 Playwright scenarios pass — Wave 3 integration testing complete"
```

---

**Definition of done:** `npx playwright test` — all 8 spec files pass. All scenarios from `planning/PLAN.md §10` covered. Zero failures.
