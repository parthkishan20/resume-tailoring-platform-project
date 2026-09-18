// test/e2e/07-assistant.spec.ts
import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import { join } from "path";
import { MOCK_CHAT_RESPONSE } from "../fixtures/mock-constants";
import {
  clearAllResumes,
  confirmAlertDialog,
  resetChat,
  sendChatMessage,
  setMasterResume,
} from "./helpers";

const SAMPLE_YAML = readFileSync(join(__dirname, "../fixtures/sample-resume.yaml"), "utf-8");

test.describe("Assistant", () => {
  test.beforeEach(async ({ request }) => {
    await setMasterResume(request, SAMPLE_YAML);
    await clearAllResumes(request);
    await resetChat(request);
  });

  test("sending a message renders the reply from the deterministic stub", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=inspector-tab-assistant]").click();

    await expect(page.locator("[data-testid=chat-input]")).toBeVisible();
    await sendChatMessage(page, "Hello, what can you do?");

    await expect(page.locator("[data-testid=chat-message]")).toHaveCount(2, { timeout: 15_000 });
    await expect(page.locator("[data-testid=chat-message]").last()).toContainText(
      MOCK_CHAT_RESPONSE,
    );
  });

  test("a suggestion chip fills the input", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=inspector-tab-assistant]").click();

    await page.locator("[data-testid=chat-suggestion]").first().click();
    await expect(page.locator("[data-testid=chat-input]")).not.toHaveValue("");
  });

  test("a tool-triggering message produces a workstation action", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=inspector-tab-assistant]").click();

    // The deterministic stub (backend/src/resumetailor/llm/stub.py) fires the
    // update_generation_rules tool whenever the message contains this exact
    // phrase, independent of any real model's judgement (D-33 / ADR 0005).
    //
    // Deliberately not the "edit my master resume" trigger: that one's fixed
    // arguments are MOCK_GENERATION_RESULT_YAML, whose phone number
    // ("+10000000000") fails resume_schema.validate's real phonenumbers
    // check. edit_master_resume calls that strict validator (unlike the
    // save/generate paths, which call the lenient normalize_to_rendercv that
    // prunes an invalid phone instead of rejecting it), so under LLM_MOCK the
    // edit_master_resume tool deterministically returns a validation-failure
    // tool result and never completes — no trigger phrasing fixes this, only
    // a fixture or backend change (logged in docs/reports/4-4.1.md; not this
    // task's file to fix, `llm/stub.py` and `domain/assistant.py` are
    // `llm`/`backend-domain`'s).
    await sendChatMessage(page, "Please update my generation rules for me.");

    await expect(page.locator("[data-testid=chat-action-note]")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("clearing the conversation empties the transcript", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-testid=inspector-tab-assistant]").click();

    await sendChatMessage(page, "Hello");
    await expect(page.locator("[data-testid=chat-message]")).toHaveCount(2, { timeout: 15_000 });

    await page.locator("[data-testid=chat-clear]").click();
    await confirmAlertDialog(page);

    await expect(page.locator("[data-testid=chat-message]")).toHaveCount(0, { timeout: 15_000 });
  });
});
