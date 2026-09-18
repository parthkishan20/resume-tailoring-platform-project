"use client";

import * as React from "react";
import { Gauge } from "@phosphor-icons/react";
import { Button, Chip, EmptyState, ErrorState, ScoreDial, Skeleton } from "@/design-system";
import { useResumeDetail } from "@/features/queries";
import { JobDescriptionField } from "@/features/workspace/JobDescriptionField";
import { useWorkspace } from "@/features/workspace/WorkspaceContext";
import { streamEvaluate } from "@/lib/api";
import type { EvaluationResult } from "@/lib/types";

interface RunState {
  status: "idle" | "running" | "error" | "success";
  result: EvaluationResult | null;
  error: string | null;
}

const IDLE: RunState = { status: "idle", result: null, error: null };

/**
 * Evaluate (DESIGN-SYSTEM.md 3.2): the same job description as Tailor, scored
 * against "whatever document is currently in the centre" — not always the
 * master.
 *
 * ## D-45's back half, and D-41
 *
 * Task 2.3 could only reproduce the request and the result; the interim panel
 * scored the master's last *saved* copy regardless of what was open or
 * edited. `domain/evaluation.py` already accepts arbitrary YAML (2.5), so
 * closing both defects here is entirely a matter of picking the right
 * document and reading it live:
 *
 * - **Master is open** (`destination === "master"`): `masterYaml` from
 *   `WorkspaceContext` is the editor's live buffer, already up to the last
 *   keystroke, no save required — unlike Tailor, this route accepts arbitrary
 *   YAML, so there is nothing to persist first.
 * - **A generated resume is open** (`destination === "library"`): its
 *   `yaml_content` when the caller already has it (a resume just produced by
 *   Tailor's `done` event carries the full row), otherwise fetched via
 *   `useResumeDetail`, because `GET /api/resumes` list rows omit it. Nothing
 *   here can be "live" the way the master's buffer is: task 3.2 owns making
 *   the Library editable, and until it does, the document's stored content is
 *   the only copy that exists.
 * - **Library is open with nothing selected**: nothing to evaluate. A
 *   dedicated empty state says so rather than silently falling back to the
 *   master, which would evaluate a document the user cannot see on screen.
 */
export function EvaluatePanel() {
  const { jobDescription, destination, masterYaml, selectedResume } = useWorkspace();

  const targetName =
    destination === "master" ? "the master resume" : (selectedResume?.name ?? null);
  const detailId =
    destination === "library" &&
    selectedResume !== null &&
    selectedResume.yaml_content === undefined
      ? selectedResume.id
      : null;
  const needsDetail = detailId !== null;
  const detail = useResumeDetail(detailId);

  const targetYaml =
    destination === "master"
      ? masterYaml
      : (selectedResume?.yaml_content ?? detail.data?.yaml_content ?? null);

  const nothingSelected = destination === "library" && selectedResume === null;
  const targetLoading = needsDetail && detail.isPending;
  const targetLoadError = needsDetail && detail.isError ? detail.error.message : null;

  const [run, setRun] = React.useState<RunState>(IDLE);
  const abortRef = React.useRef<AbortController | null>(null);
  React.useEffect(() => () => abortRef.current?.abort(), []);

  // Whatever result is on screen was scored against the *previous* target;
  // switching documents invalidates it rather than leaving a stale score
  // attached to a different resume's name.
  const targetKey = destination === "master" ? "master" : (selectedResume?.id ?? "none");
  React.useEffect(() => {
    abortRef.current?.abort();
    setRun(IDLE);
  }, [targetKey]);

  const jdReady = jobDescription.trim().length > 0;
  const ready = jdReady && targetYaml !== null && !targetLoading;
  const running = run.status === "running";

  async function evaluate() {
    if (running || !ready || targetYaml === null) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRun({ status: "running", result: null, error: null });

    try {
      for await (const frame of streamEvaluate(
        { yaml_content: targetYaml, job_description: jobDescription },
        { signal: controller.signal },
      )) {
        if (frame.event === "done") {
          setRun({ status: "success", result: frame.data.result, error: null });
        } else if (frame.event === "error") {
          setRun({ status: "error", result: null, error: frame.data.error });
          return;
        }
      }
    } catch (caught: unknown) {
      if (controller.signal.aborted) return;
      setRun({
        status: "error",
        result: null,
        error: caught instanceof Error ? caught.message : "Evaluation failed",
      });
    }
  }

  return (
    <div className="flex flex-col gap-lp-5">
      <JobDescriptionField
        id="evaluate-job-description"
        label="Job description"
        testId="evaluate-job-description"
        disabled={running}
      />

      {destination === "library" ? (
        <p className="font-lp-sans text-lp-caption text-lp-ink-tertiary">
          {nothingSelected
            ? "Nothing is open in the Library."
            : `Evaluating ${targetName ?? "this resume"}.`}
        </p>
      ) : null}

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
        {destination === "master" ? "Evaluate the master resume" : "Evaluate this resume"}
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
      ) : run.status === "error" ? (
        <ErrorState
          title="The resume was not evaluated"
          cause={run.error ?? undefined}
          action={
            <Button
              variant="secondary"
              size="sm"
              data-testid="evaluate-retry"
              onClick={() => void evaluate()}
            >
              Try again
            </Button>
          }
        />
      ) : targetLoadError ? (
        <ErrorState
          title="This resume could not be loaded"
          cause={targetLoadError}
          action={
            <Button variant="secondary" size="sm" onClick={() => void detail.refetch()}>
              Try again
            </Button>
          }
        />
      ) : run.status === "success" && run.result ? (
        <Result result={run.result} />
      ) : nothingSelected ? (
        <EmptyState
          icon={<Gauge size={22} />}
          title="Select a document to evaluate"
          description="Open the master resume, or choose one from the Library, then come back here."
        />
      ) : (
        <EmptyState
          icon={<Gauge size={22} />}
          title={jdReady ? "Ready to evaluate" : "Paste a job description"}
          description={
            jdReady
              ? `Scores ${targetName ?? "the open document"} against this posting.`
              : "Evaluate reports a match score, a critique, and the keywords you are missing."
          }
        />
      )}
    </div>
  );
}

function Result({ result }: { result: EvaluationResult }) {
  return (
    <div data-testid="evaluate-result" className="flex flex-col gap-lp-5">
      <ScoreDial score={result.match_score} />

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
