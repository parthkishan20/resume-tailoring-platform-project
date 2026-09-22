"use client";

import { Chip, Tooltip, type ChipTone } from "@/design-system";
import { useLlmUsage } from "@/features/queries";

/** Either window at or above this fraction of its limit reads as `critical`. */
const NEAR_LIMIT_RATIO = 0.8;

/**
 * The free-tier rate-limit counter, next to the assistant.
 *
 * `openrouter/free` (ADR 0008) allows a fixed number of requests per minute
 * and per UTC calendar day, shared across every surface that calls the LLM
 * (Chat, Tailor, Evaluate, PDF import) — not scoped to this panel, which is
 * why it says so in the tooltip rather than implying "messages left."
 *
 * Renders nothing until the first poll resolves (`useLlmUsage`), and nothing
 * again if it errors: a stale or missing count is not worth a fallback UI of
 * its own, next to a conversation the user is actually trying to have.
 */
export function UsageCounter() {
  const { data } = useLlmUsage();
  if (!data) return null;

  const minuteRatio = data.minute_count / data.minute_limit;
  const dayRatio = data.day_count / data.day_limit;
  const tone: ChipTone = Math.max(minuteRatio, dayRatio) >= NEAR_LIMIT_RATIO ? "critical" : "neutral";

  return (
    <Tooltip
      label={`${data.minute_count} of ${data.minute_limit} LLM requests used this minute, ${data.day_count} of ${data.day_limit} today. Shared across Chat, Tailor, Evaluate and PDF import. Resets at midnight UTC.`}
    >
      <Chip tone={tone} data-testid="llm-usage-counter">
        {data.minute_count}/{data.minute_limit} · {data.day_count}/{data.day_limit}
      </Chip>
    </Tooltip>
  );
}
