"use client";

import * as React from "react";
import { Gauge } from "@phosphor-icons/react";
import { Button, Chip, EmptyState, ErrorState, Skeleton } from "@/design-system";
import { JobDescriptionField } from "@/features/workspace/JobDescriptionField";
import { useWorkspace } from "@/features/workspace/WorkspaceContext";
import { readSseStream } from "@/lib/sse";
import type { EvaluationResult, MasterResume } from "@/lib/types";

/**
 * Score bands. Three of them, with text labels, because section 5 forbids
 * communicating the score by colour alone: the numeral and the band name each
 * carry it independently.
 */
function band(score: number): { label: string; tone: "positive" | "caution" | "critical" } {
  if (score >= 75) return { label: "Strong match", tone: "positive" };
  if (score >= 50) return { label: "Partial match", tone: "caution" };
  return { label: "Weak match", tone: "critical" };
}

const TONE_TEXT = {
  positive: "text-lp-positive",
  caution: "text-lp-caution",
  critical: "text-lp-critical",
} as const;

/**
 * Evaluate (DESIGN-SYSTEM.md 3.2): the same job description as Tailor, scored
 * against the document in the centre.
 *
 * ## Where the line between task 2.3 and task 3.1 falls
 *
 * As with Tailor, the old 175-line `EvaluationPanel` is a page and cannot be
 * re-hosted in a 380px rail, so the request is reproduced and the result is
 * rendered with the primitives 1.4 shipped.
 *
 * Two deliberate gaps, both 3.1's:
 *
 * 1. `ScoreDial` is specified in 4.1 and task 1.4 did not ship it, so the
 *    score renders as a tabular numeral over a band label. That satisfies
 *    section 5 but it is not the drawn dial the spec asks for, and building a
 *    design-system primitive is not this task's to do.
 * 2. The document being scored is still the master resume. D-45 (score the
 *    generated resume, not only the master) needs the generated document's
 *    YAML, which means a second fetch and a decision about which document the
 *    centre is showing. That is feature logic and it is 3.1's.
 */
export function EvaluatePanel({ masterResume }: { masterResume: MasterResume }) {
  const { jobDescription } = useWorkspace();
  const [result, setResult] = React.useState<EvaluationResult | null>(null);
  const [status, setStatus] = React.useState<"idle" | "running" | "error">("idle");
  const [error, setError] = React.useState<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  const ready = jobDescription.trim().length > 0;
  const running = status === "running";

  async function evaluate() {
    if (running || !ready) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("running");
    setError(null);
    setResult(null);

    try {
      for await (const event of readSseStream(
        "/api/evaluate/stream",
        { yaml_content: masterResume.yaml_content, job_description: jobDescription },
        controller.signal,
      )) {
        if (event.event === "done") {
          setResult((event.data as { result: EvaluationResult }).result);
        } else if (event.event === "error") {
          setError((event.data as { error: string }).error);
          setStatus("error");
          return;
        }
      }
    } catch (caught: unknown) {
      if (controller.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : "Evaluation failed");
      setStatus("error");
      return;
    }
    setStatus("idle");
  }

  return (
    <div className="flex flex-col gap-lp-5">
      <JobDescriptionField
        id="evaluate-job-description"
        label="Job description"
        disabled={running}
      />

      <Button
        data-testid="evaluate-button"
        variant="primary"
        icon={<Gauge size={15} />}
        onClick={() => void evaluate()}
        loading={running}
        loadingLabel="Evaluating"
        disabled={!ready}
        className="w-full"
      >
        Evaluate this resume
      </Button>

      {running ? (
        <div aria-busy="true" className="flex flex-col gap-lp-4">
          <p aria-live="polite" className="sr-only">
            Reading the resume against the role
          </p>
          <Skeleton shape="block" className="h-lp-8 w-[120px]" />
          <div className="flex flex-col gap-lp-2">
            <Skeleton shape="text" />
            <Skeleton shape="text" />
            <Skeleton shape="text" className="w-2/3" />
          </div>
        </div>
      ) : status === "error" ? (
        <ErrorState
          title="The resume was not evaluated"
          cause={error ?? undefined}
          action={
            <Button variant="secondary" size="sm" onClick={() => void evaluate()}>
              Try again
            </Button>
          }
        />
      ) : result ? (
        <Result result={result} />
      ) : (
        <EmptyState
          icon={<Gauge size={22} />}
          title={ready ? "Ready to evaluate" : "Paste a job description"}
          description={
            ready
              ? "Scores the master resume against this posting."
              : "Evaluate reports a match score, a critique, and the keywords you are missing."
          }
        />
      )}
    </div>
  );
}

function Result({ result }: { result: EvaluationResult }) {
  const { label, tone } = band(result.match_score);

  return (
    <div data-testid="evaluate-result" className="flex flex-col gap-lp-5">
      <div
        role="img"
        aria-label={`Match score ${result.match_score} out of 100. ${label}.`}
        className="flex items-baseline gap-lp-3"
      >
        <span className="font-lp-mono text-lp-display font-semibold tabular-nums text-lp-ink">
          {result.match_score}
        </span>
        <span className="font-lp-sans text-lp-caption text-lp-ink-tertiary">/ 100</span>
        <span className={`font-lp-sans text-lp-label font-medium ${TONE_TEXT[tone]}`}>{label}</span>
      </div>

      <p className="max-w-[65ch] font-lp-sans text-lp-body text-lp-ink">{result.critique}</p>

      <div className="flex flex-col gap-lp-4">
        <KeywordGroup
          heading="Matched keywords"
          toneLabel="Matched"
          chipTone="positive"
          keywords={result.matched_keywords}
          emptyCopy="None of the posting's keywords were found."
        />
        <KeywordGroup
          heading="Missing keywords"
          toneLabel="Missing"
          chipTone="critical"
          keywords={result.missing_keywords}
          emptyCopy="Nothing is missing."
        />
      </div>
    </div>
  );
}

function KeywordGroup({
  heading,
  toneLabel,
  chipTone,
  keywords,
  emptyCopy,
}: {
  heading: string;
  toneLabel: string;
  chipTone: "positive" | "critical";
  keywords: string[];
  emptyCopy: string;
}) {
  return (
    <section className="flex flex-col gap-lp-2">
      <h3 className="font-lp-sans text-lp-heading font-semibold text-lp-ink">
        {heading}{" "}
        <span className="font-lp-mono text-lp-caption font-normal tabular-nums text-lp-ink-tertiary">
          {keywords.length}
        </span>
      </h3>
      {keywords.length === 0 ? (
        <p className="font-lp-sans text-lp-caption text-lp-ink-tertiary">{emptyCopy}</p>
      ) : (
        <ul className="flex flex-wrap gap-lp-1">
          {keywords.map((keyword) => (
            <li key={keyword}>
              <Chip tone={chipTone} toneLabel={toneLabel}>
                {keyword}
              </Chip>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
