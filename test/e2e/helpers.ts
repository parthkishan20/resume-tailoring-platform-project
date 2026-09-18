// test/e2e/helpers.ts — shared setup/reset helpers for the e2e suite.
//
// Every spec is responsible for the state it needs (AGENTS.md §9, D-29):
// no spec may assume residue left by another spec or by a previous run.
// These helpers are the one place that state-reset logic lives, since eight
// specs otherwise repeat the same four API calls.
import type { APIRequestContext, Page } from "@playwright/test";

export async function resetMasterResume(request: APIRequestContext): Promise<void> {
  await request.delete("/api/master-resume").catch(() => {});
}

export async function setMasterResume(request: APIRequestContext, yamlContent: string): Promise<void> {
  const response = await request.put("/api/master-resume", { data: { yaml_content: yamlContent } });
  if (!response.ok()) {
    throw new Error(`Failed to seed master resume: ${response.status()} ${await response.text()}`);
  }
}

export async function resetChat(request: APIRequestContext): Promise<void> {
  await request.delete("/api/chat").catch(() => {});
}

export async function resetRules(request: APIRequestContext): Promise<void> {
  await request.delete("/api/rules").catch(() => {});
}

interface ResumeListPage {
  items: Array<{ id: number }>;
  total: number;
}

/** Deletes every generated resume, so a spec that lists or counts them starts from zero. */
export async function clearAllResumes(request: APIRequestContext): Promise<void> {
  const existing = await request.get("/api/resumes", { params: { limit: 100 } });
  if (!existing.ok()) throw new Error(`Failed to list resumes: ${existing.status()}`);
  const page = (await existing.json()) as ResumeListPage;
  for (const row of page.items) {
    await request.delete(`/api/resumes/${row.id}`);
  }
}

/**
 * Generates one resume through the real streaming pipeline (LLM_MOCK, so this
 * is fast and deterministic) and waits for the terminal `done` event. Used to
 * seed the library for specs that need existing generated resumes rather than
 * driving Tailor through the UI.
 *
 * `POST /api/resumes/stream` is one of the four endpoints `core/security.py`
 * rate-limits (burst 6, 12/minute, one token bucket for the whole running
 * app, shared across every spec in the suite). A spec that seeds more than a
 * handful of resumes will legitimately get a 429; this honours the server's
 * `Retry-After` header rather than treating the limiter as a bug to work
 * around some other way.
 */
export async function createResume(request: APIRequestContext, jobDescription: string): Promise<void> {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const response = await request.post("/api/resumes/stream", {
      data: { job_description: jobDescription },
      timeout: 60_000,
    });
    if (response.status() === 429) {
      const retryAfter = Number(response.headers()["retry-after"] ?? "5");
      await new Promise((resolve) => setTimeout(resolve, (retryAfter + 0.5) * 1000));
      continue;
    }
    if (!response.ok()) {
      throw new Error(`Resume generation request failed: ${response.status()}`);
    }
    const body = await response.text();
    if (!body.includes("event: done") || body.includes("event: error")) {
      throw new Error(`Resume generation did not complete: ${body}`);
    }
    return;
  }
  throw new Error("Resume generation kept hitting the rate limiter after 10 attempts");
}

/**
 * Confirms a Radix `AlertDialog` (design-system's `AlertDialogContent`, used
 * for every destructive confirmation: delete master resume, delete a
 * generated resume, delete a library row, clear the chat).
 *
 * `AlertDialogContent`'s Confirm/Cancel actions carry no `data-testid`
 * (logged as a blocker in PLAN.md open blockers — `qa-e2e` does not own
 * `design-system/`), so this cannot select the confirm button by testid or by
 * its label without violating the data-testid-only convention.
 *
 * This clicks the last button inside `[role="alertdialog"]` (Confirm always
 * renders after Cancel in `AlertDialogContent`) — a structural, not textual,
 * locator. An earlier version of this helper drove the dialog by keyboard
 * (Tab from Radix's documented initial focus on Cancel, then Enter), which
 * worked for the master-resume delete dialog but silently failed for the
 * Library's per-row delete dialog: `ResumeListRow` (`features/library/
 * ResumeList.tsx`) attaches an `onKeyDown` for its own Enter/Space-to-select
 * behaviour directly on the row, and because Radix's dialog content is
 * portalled to `document.body` while staying a React *child* of that row,
 * React's synthetic Enter keydown bubbles through the component tree (not
 * the DOM tree) into the row's handler, which calls `preventDefault()` before
 * the dialog's own Action button ever sees it. Confirmed by tracing network
 * requests: the keyboard path never issued the DELETE call. A real mouse
 * click does not go through `onKeyDown` at all, so it is unaffected — logged
 * as a defect (`docs/reports/4-4.1.md`) rather than routed around silently.
 */
export async function confirmAlertDialog(page: Page): Promise<void> {
  await page.locator('[role="alertdialog"]').waitFor({ state: "visible" });
  await page.locator('[role="alertdialog"] button').last().click();
}

/**
 * Submits `RenameResumeDialog` (a Radix `Dialog`, distinct from the
 * `AlertDialog` above) by clicking its submit button rather than pressing
 * Enter in the `rename-input` field. Enter would normally submit a
 * single-input form natively, but when the dialog is opened from a Library
 * list row it hits the same `ResumeListRow` keydown-bubbling issue
 * documented on `confirmAlertDialog`, so this uses the same click-based
 * workaround for consistency, even where (e.g. the document header) it is
 * not strictly required.
 */
export async function submitRenameDialog(page: Page): Promise<void> {
  await page.locator('[role="dialog"] button[type="submit"]').click();
}

/**
 * Sends a chat message through the UI, retrying through the product's own
 * `chat-retry` affordance if the app-wide rate limiter (`core/security.py`)
 * answers with a transient failure.
 *
 * `POST /api/chat/stream` is one of the four rate-limited endpoints and
 * shares its token bucket with `/api/resumes/stream` and
 * `/api/evaluate/stream` — the same bucket 06-library.spec.ts's pagination
 * test (22 resumes) draws down. A spec running soon after can still find the
 * bucket recovering. This is not a product bug to route around silently: it
 * is the intended behaviour of a real rate limiter under real load, so this
 * uses the same UI path a user would (the visible Retry button `Chat.tsx`
 * already renders on a failed send) rather than bypassing the UI.
 */
export async function sendChatMessage(page: Page, message: string): Promise<void> {
  await page.locator("[data-testid=chat-input]").fill(message);
  await page.locator("[data-testid=chat-send]").click();
  await retryOnRateLimit(page, "chat-retry");
}

/**
 * After clicking a button that starts a rate-limited request (Tailor's
 * Generate, Evaluate's Evaluate), waits briefly for that panel's own "Try
 * again" affordance and clicks it if the app-wide rate limiter answered with
 * a transient failure. See `sendChatMessage`'s doc comment for why this
 * suite can hit the limiter under its own load, independent of anything
 * being wrong with the product.
 */
async function retryOnRateLimit(page: Page, retryTestId: string): Promise<void> {
  const retryButton = page.locator(`[data-testid=${retryTestId}]`);
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const failed = await retryButton
      .waitFor({ state: "visible", timeout: 3_000 })
      .then(() => true)
      .catch(() => false);
    if (!failed) return;
    await new Promise((resolve) => setTimeout(resolve, 5_000));
    await retryButton.click();
  }
}

/** Clicks Tailor's Generate button, retrying through `tailor-retry` on a transient rate limit. */
export async function clickGenerate(page: Page): Promise<void> {
  await page.locator("[data-testid=generate-button]").click();
  await retryOnRateLimit(page, "tailor-retry");
}

/** Clicks Evaluate's Evaluate button, retrying through `evaluate-retry` on a transient rate limit. */
export async function clickEvaluate(page: Page): Promise<void> {
  await page.locator("[data-testid=evaluate-button]").click();
  await retryOnRateLimit(page, "evaluate-retry");
}
