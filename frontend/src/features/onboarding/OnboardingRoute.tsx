"use client";

import * as React from "react";
import { FilePdf, UploadSimple } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { Button, cn, ErrorState, useToast } from "@/design-system";
import { queryKeys, useSaveMasterResume } from "@/features/queries";
import { api } from "@/lib/api";
import type { MasterResume } from "@/lib/types";
import { SAMPLE_YAML, SKELETON_YAML } from "./sample";

/**
 * First run (DESIGN-SYSTEM.md 3.3), the one high-variance surface in the
 * product: `DESIGN_VARIANCE: 6`, an asymmetric split rather than a centred
 * stack, and three ranked entry paths with exactly one primary.
 *
 * ## D-39, the other live P0
 *
 * The old drop zone was a bare `<div onClick>` wrapping a `display: none` file
 * input: no role, no `tabIndex`, no key handler, and an input that was out of
 * the tab order, so there was no keyboard path at all to the primary
 * onboarding action. Task 0.6 is still open in `PLAN.md` and the old
 * `components/EmptyState.tsx` still has the defect.
 *
 * The pattern here is the one that does not need a key handler to be correct:
 * a real `<input type="file">` kept in the accessibility tree and the tab
 * order with `sr-only` rather than removed from both with `display: none`, and
 * a `<label>` bound to it carrying the visible target. Tab reaches the input,
 * Enter and Space open the picker, a pointer click on the zone opens it
 * through the label, and the drop handler is additive rather than the only way
 * in. `focus-within` puts the focus ring on the zone, so the focused control
 * is visible even though the input itself is not.
 *
 * ## What the spec asks for here that is not built
 *
 * 3.3 wants the right column to carry "a real rendered sample resume page at
 * `--shadow-page`, which is the honest product screenshot (it is a real PDF
 * render, not a div mock)". There is no PDF to render on this screen: the
 * render endpoints work from the stored master resume, and on first run there
 * is not one. Rather than mock a page, the column shows the real sample in its
 * real source form, which is the artifact the two non-import paths actually
 * create. Rendering a page here needs a backend endpoint that renders
 * arbitrary YAML without storing it, which no task currently owns.
 */
export function OnboardingRoute() {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [importing, setImporting] = React.useState(false);
  const [dragging, setDragging] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const save = useSaveMasterResume();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  async function importPdf(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("That is not a PDF. Choose a file ending in .pdf.");
      return;
    }
    setImporting(true);
    setError(null);
    try {
      const imported: MasterResume = await api.importPdf(file);
      toast({ title: "Resume imported", tone: "positive" });
      // The shell reads the master resume from the query cache, so writing the
      // response straight into it is what moves the user into the workspace,
      // with no refetch of something the server has just handed us.
      queryClient.setQueryData(queryKeys.masterResume, imported);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The PDF could not be imported.");
    } finally {
      setImporting(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function seed(yaml: string, successTitle: string) {
    setError(null);
    save.mutate(yaml, {
      onSuccess: () => toast({ title: successTitle, tone: "positive" }),
      onError: (caught) => setError(caught.message),
    });
  }

  return (
    <main
      data-testid="empty-state"
      className="min-h-[100dvh] bg-lp-paper px-lp-5 py-lp-7 font-lp-sans lg:px-lp-8"
    >
      <div className="mx-auto grid max-w-[1180px] items-start gap-lp-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
        <div className="flex flex-col gap-lp-6">
          <p className="font-lp-mono text-lp-caption uppercase tracking-[0.12em] text-lp-ink-tertiary">
            ResumeTailor
          </p>

          <h1 className="max-w-[22ch] text-lp-display font-semibold text-lp-ink">
            One master resume. <span className="italic">Cut</span> to fit each role.
          </h1>

          <p className="max-w-[52ch] text-lp-body text-lp-ink-secondary">
            Keep your history in one place and let each application take only what it needs.
          </p>

          <div className="flex flex-col gap-lp-4">
            <div
              data-testid="pdf-import-zone"
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                const file = event.dataTransfer.files[0];
                if (file) void importPdf(file);
              }}
              className={cn(
                "rounded-lp-surface border-2 border-dashed p-lp-6",
                "focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-lp-focus",
                dragging
                  ? "border-lp-accent bg-lp-accent-wash"
                  : "border-lp-rule-control bg-lp-paper-raised hover:border-lp-rule-strong",
              )}
            >
              <input
                ref={inputRef}
                id="pdf-import-input"
                type="file"
                accept="application/pdf,.pdf"
                disabled={importing}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void importPdf(file);
                }}
                // `sr-only`, never `hidden`: the input has to stay in the
                // accessibility tree and the tab order for this to be
                // reachable without a pointer at all (D-39).
                className="sr-only"
              />
              <label
                htmlFor="pdf-import-input"
                className="flex cursor-pointer flex-col items-start gap-lp-2"
              >
                <span className="flex h-lp-control-primary w-lp-control-primary items-center justify-center rounded-lp-control bg-lp-accent-wash text-lp-accent">
                  <UploadSimple size={20} aria-hidden="true" />
                </span>
                <span className="text-lp-heading font-semibold text-lp-ink">
                  {importing ? "Reading your PDF" : "Import a resume PDF"}
                </span>
                <span className="text-lp-caption text-lp-ink-tertiary">
                  Drop it here, or press Enter to choose a file.
                </span>
              </label>
              <p aria-live="polite" className="sr-only">
                {importing ? "Converting your PDF to YAML." : ""}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-lp-3">
              <Button
                variant="secondary"
                data-testid="onboarding-sample"
                onClick={() => seed(SAMPLE_YAML, "Sample resume loaded")}
                loading={save.isPending}
                loadingLabel="Loading"
              >
                Start from the sample
              </Button>
              <button
                type="button"
                data-testid="onboarding-scratch"
                onClick={() => seed(SKELETON_YAML, "Empty resume created")}
                className={cn(
                  "text-lp-label font-medium text-lp-accent underline underline-offset-4",
                  "hover:text-lp-accent-hover",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
                )}
              >
                Write YAML from scratch
              </button>
            </div>

            {error ? <ErrorState title="That did not work" cause={error} /> : null}
          </div>
        </div>

        <aside aria-label="Sample resume" className="min-w-0">
          <div className="overflow-hidden rounded-lp-surface bg-lp-paper-raised shadow-lp-page">
            <div className="flex h-lp-panel-header items-center gap-lp-2 border-b border-lp-rule px-lp-4">
              <FilePdf size={16} aria-hidden="true" className="text-lp-ink-tertiary" />
              <span className="font-lp-mono text-lp-caption text-lp-ink-secondary">
                master-resume.yaml
              </span>
              <a
                href={`data:text/yaml;charset=utf-8,${encodeURIComponent(SAMPLE_YAML)}`}
                download="master-resume.yaml"
                data-testid="onboarding-download"
                className={cn(
                  "ml-auto text-lp-caption font-medium text-lp-accent underline underline-offset-4",
                  "hover:text-lp-accent-hover",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
                )}
              >
                Download
              </a>
            </div>
            <pre className="max-h-[52dvh] overflow-auto p-lp-4 font-lp-mono text-lp-code text-lp-ink">
              {SAMPLE_YAML}
            </pre>
          </div>
        </aside>
      </div>
    </main>
  );
}
