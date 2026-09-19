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
 * `POST /api/resumes/stream` now accepts an optional `yaml_content` override
 * (B-06), so Tailor sends `masterYaml` — the live editor buffer, whether or
 * not it has unsaved edits — straight into the request, the same way Evaluate
 * already sends it to `/api/evaluate/stream`. No save-before-generate step is
 * needed on the primary path any more: the document the backend tailors is
 * always the one on screen, not a saved copy that might be stale.
 */
export function TailorPanel({ onEditRules }: { onEditRules: () => void }) {
  const { jobDescription, openResume, setInspectorTab, masterYaml } = useWorkspace();
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

    let produced: GeneratedResume | null = null;
    try {
      for await (const frame of streamTailor(
        { job_description: jobDescription, yaml_content: masterYaml },
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
