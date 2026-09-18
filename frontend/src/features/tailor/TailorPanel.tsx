"use client";

import * as React from "react";
import { PencilSimple, Scissors } from "@phosphor-icons/react";
import { Button, EmptyState, ErrorState, ProgressRail, type ProgressStage } from "@/design-system";
import { useInvalidateResumes, useRules } from "@/features/queries";
import { JobDescriptionField } from "@/features/workspace/JobDescriptionField";
import { useWorkspace } from "@/features/workspace/WorkspaceContext";
import { streamTailor } from "@/lib/api";
import type { GeneratedResume } from "@/lib/types";

/**
 * The three stages the backend actually reports, in the order it reports them
 * (`api/routers/resumes.py`, the three `progress` events). Named here rather
 * than invented: section 7 forbids fake-precise copy, and a rail with stages
 * the server never reaches would be exactly that.
 */
const STAGES: ProgressStage[] = [
  { id: "analyze", label: "Analyzing the job description" },
  { id: "tailor", label: "Tailoring the content" },
  { id: "render", label: "Rendering the PDF" },
];

/** Maps a backend progress message onto a stage index. */
function stageIndexFor(message: string): number {
  const lowered = message.toLowerCase();
  if (lowered.startsWith("rendering")) return 2;
  if (lowered.startsWith("tailoring")) return 1;
  return 0;
}

interface RunState {
  status: "idle" | "running" | "error" | "complete";
  stageIndex: number;
  error: string | null;
}

const IDLE: RunState = { status: "idle", stageIndex: 0, error: null };

/**
 * Tailor (DESIGN-SYSTEM.md 3.2): the shared job description, a summary of the
 * generation rules with an inline edit affordance, the stage rail while a run
 * is in flight, and the handoff that opens the finished document in the
 * centre.
 *
 * ## Where the line between task 2.3 and task 3.1 falls
 *
 * The 182-line `GenerationPanel` could not be re-hosted here. It is a page: a
 * 52px header over a fixed 420px input rail beside a fluid result column, and
 * the inspector is 380px wide with a 560px ceiling. What is reproduced is the
 * request and the handoff, about twenty lines of it, because retiring the old
 * shell without them would make generation unreachable in the product. What is
 * left for 3.1 is everything that is actually the feature: the result surface,
 * the five states of 4.3, retry that preserves partial work, and evaluating
 * the generated document rather than the master (D-45, D-41).
 *
 * ## D-41, the half that is Tailor's
 *
 * `POST /api/resumes/stream` tailors whatever `master_resume` currently holds
 * in the database; it takes no document override (unlike
 * `/api/evaluate/stream`, which accepts arbitrary YAML, so Evaluate can read
 * the live buffer directly). Adding one is an API-contract change outside
 * this task's file ownership (`api/routers/resumes.py` belongs to
 * `api-contract`/`backend-domain`; see the blocker recorded in
 * `docs/reports/3-3.1.md`). The fix available here: if the master buffer has
 * unsaved edits when the user starts a run, they are saved first, so the
 * document the backend reads back out is always the one on screen, not a
 * stale saved copy. A failed save aborts the run rather than silently
 * tailoring the old document.
 */
export function TailorPanel({ onEditRules }: { onEditRules: () => void }) {
  const { jobDescription, openResume, setInspectorTab, masterDirty, saveMasterDraft } =
    useWorkspace();
  const invalidateResumes = useInvalidateResumes();
  const rules = useRules();

  const [run, setRun] = React.useState<RunState>(IDLE);
  const abortRef = React.useRef<AbortController | null>(null);

  // Section 7: every SSE subscription has cleanup. The old panels passed no
  // signal at all, so navigating away orphaned a 30 second job (P0-6).
  React.useEffect(() => () => abortRef.current?.abort(), []);

  const ready = jobDescription.trim().length > 0;
  const running = run.status === "running";

  async function generate() {
    if (running || !ready) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRun({ status: "running", stageIndex: 0, error: null });

    if (masterDirty) {
      try {
        await saveMasterDraft();
      } catch (error: unknown) {
        setRun({
          status: "error",
          stageIndex: 0,
          error:
            error instanceof Error
              ? `Your unsaved edits could not be saved: ${error.message}`
              : "Your unsaved edits could not be saved",
        });
        return;
      }
    }

    let produced: GeneratedResume | null = null;
    try {
      for await (const frame of streamTailor(
        { job_description: jobDescription },
        { signal: controller.signal },
      )) {
        if (frame.event === "progress") {
          setRun((current) => ({ ...current, stageIndex: stageIndexFor(frame.data.message) }));
        } else if (frame.event === "done") {
          produced = frame.data.result;
        } else if (frame.event === "error") {
          setRun((current) => ({ ...current, status: "error", error: frame.data.error }));
          return;
        }
      }
    } catch (error: unknown) {
      if (controller.signal.aborted) return;
      setRun((current) => ({
        ...current,
        status: "error",
        error: error instanceof Error ? error.message : "Generation failed",
      }));
      return;
    }

    if (produced) {
      setRun({ status: "complete", stageIndex: STAGES.length - 1, error: null });
      invalidateResumes();
      // The handoff 3.2 specifies: the new document opens in the centre and
      // the inspector moves to Evaluate, which is where the user goes next.
      openResume(produced);
      setInspectorTab("evaluate");
    } else {
      setRun(IDLE);
    }
  }

  const ruleCount = rules.data?.length ?? 0;

  return (
    <div className="flex flex-col gap-lp-5">
      <JobDescriptionField
        id="tailor-job-description"
        label="Job description"
        testId="job-description"
        disabled={running}
      />

      <Button
        data-testid="generate-button"
        variant="primary"
        icon={<Scissors size={15} />}
        onClick={() => void generate()}
        loading={running}
        loadingLabel="Tailoring"
        disabled={!ready}
        className="w-full"
      >
        Tailor a resume
      </Button>

      <section aria-label="Generation rules" className="flex flex-col gap-lp-2">
        <div className="flex items-center justify-between gap-lp-2">
          <h2 className="font-lp-sans text-lp-heading font-semibold text-lp-ink">Rules</h2>
          <Button
            variant="ghost"
            size="sm"
            icon={<PencilSimple size={14} />}
            data-testid="tailor-edit-rules"
            onClick={onEditRules}
          >
            Edit
          </Button>
        </div>
        <p className="font-lp-sans text-lp-caption text-lp-ink-tertiary">
          {rules.isPending
            ? "Loading the generation rules."
            : rules.isError
              ? "The generation rules could not be loaded. Defaults apply."
              : `${ruleCount} ${ruleCount === 1 ? "rule" : "rules"} applied to every run.`}
        </p>
      </section>

      {run.status === "running" || run.status === "complete" ? (
        <ProgressRail
          stages={STAGES}
          currentIndex={run.stageIndex}
          status={run.status}
          label="Tailoring"
        />
      ) : run.status === "error" ? (
        <ErrorState
          title="The resume was not generated"
          cause={run.error ?? undefined}
          action={
            <Button
              variant="secondary"
              size="sm"
              data-testid="tailor-retry"
              onClick={() => void generate()}
            >
              Try again
            </Button>
          }
        />
      ) : (
        <EmptyState
          icon={<Scissors size={22} />}
          title={ready ? "Ready to tailor" : "Paste a job description"}
          description={
            ready
              ? "The tailored resume opens in the centre when it is ready."
              : "Tailor cuts your master resume down to what this role asks for."
          }
        />
      )}
    </div>
  );
}
