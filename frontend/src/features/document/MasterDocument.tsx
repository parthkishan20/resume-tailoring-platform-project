"use client";

import * as React from "react";
import { FloppyDisk, Trash } from "@phosphor-icons/react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTrigger,
  Button,
  cn,
  DocumentFrame,
  ErrorState,
  ModeSwitch,
  type DocumentMode,
} from "@/design-system";
import { ResizeHandle } from "@/features/workspace/ResizeHandle";
import { YamlEditor } from "./YamlEditor";

export interface MasterDocumentProps {
  yaml: string;
  onYamlChange: (next: string) => void;
  dirty: boolean;
  updatedAt: string;

  mode: DocumentMode;
  onModeChange: (mode: DocumentMode) => void;

  /** Percentage of the split given to the editor. */
  splitPercent: number;
  onSplitChange: (percent: number) => void;
  splitMin: number;
  splitMax: number;

  onSave: () => void;
  saving: boolean;
  saveError: string | null;

  onDelete: () => void;

  /** Bumped by the owner after a save so the preview refetches. */
  previewKey: number;
}

/**
 * The master resume as a document: Editor / Split / Preview over one buffer.
 *
 * Deliberately stateless about the buffer. Every piece of state that would be
 * expensive or destructive to lose lives in `DocumentRegion`, one level up,
 * which is not unmounted by navigation. That inversion is the fix for D-30 and
 * the reason this component can be unmounted freely.
 */
export function MasterDocument({
  yaml,
  onYamlChange,
  dirty,
  updatedAt,
  mode,
  onModeChange,
  splitPercent,
  onSplitChange,
  splitMin,
  splitMax,
  onSave,
  saving,
  saveError,
  onDelete,
  previewKey,
}: MasterDocumentProps) {
  const splitRef = React.useRef<HTMLDivElement>(null);

  const showEditor = mode !== "preview";
  const showPreview = mode !== "editor";
  const bothPanes = showEditor && showPreview;

  const measure = React.useCallback((event: PointerEvent) => {
    const rect = splitRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return null;
    return ((event.clientX - rect.left) / rect.width) * 100;
  }, []);

  return (
    <section aria-label="Master resume" className="flex h-full min-w-0 flex-col">
      {/*
       * Two rows below `lg`, one row from `lg` up.
       * The single row does not fit sooner than that: the mode switch, Save and
       * Delete come to about 390px on their own, so on a 840px viewport with
       * the inspector docked there is nothing left for the title, and a title
       * that can shrink to zero width disappears rather than wrapping.
       */}
      <header
        className={cn(
          "flex shrink-0 flex-col gap-lp-2 border-b border-lp-rule bg-lp-paper px-lp-4 py-lp-2",
          "lg:h-lp-panel-header lg:flex-row lg:items-center lg:justify-between lg:gap-lp-3 lg:py-0",
        )}
      >
        <div className="flex min-w-0 items-baseline gap-lp-3">
          <h1 className="truncate font-lp-sans text-lp-title font-semibold text-lp-ink">
            Master resume
          </h1>
          <span className="truncate font-lp-mono text-lp-caption tabular-nums text-lp-ink-tertiary">
            {dirty ? "Unsaved edits" : `Saved ${new Date(updatedAt).toLocaleString()}`}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-lp-2 lg:shrink-0">
          <ModeSwitch value={mode} onChange={onModeChange} />
          <Button
            data-testid="save-master-resume"
            variant="primary"
            size="sm"
            icon={<FloppyDisk size={15} />}
            onClick={onSave}
            loading={saving}
            loadingLabel="Saving"
            disabled={!dirty}
          >
            Save
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                data-testid="delete-master-resume"
                variant="ghost"
                size="sm"
                icon={<Trash size={15} />}
              >
                Delete
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent
              title="Delete the master resume?"
              description="This removes the document and its history. Tailored resumes already in the library are kept. This cannot be undone."
              confirmLabel="Delete"
              onConfirm={onDelete}
            />
          </AlertDialog>
        </div>
      </header>

      {saveError ? (
        <div className="shrink-0 border-b border-lp-rule bg-lp-paper px-lp-4 py-lp-3">
          <ErrorState
            title="The document was not saved"
            cause={saveError}
            action={
              <Button variant="secondary" size="sm" onClick={onSave}>
                Try again
              </Button>
            }
          />
        </div>
      ) : null}

      <div ref={splitRef} className="flex min-h-0 flex-1 flex-col md:flex-row">
        {showEditor ? (
          <div
            data-testid="yaml-editor"
            style={{ "--lp-split": `${splitPercent}%` } as React.CSSProperties}
            className={cn(
              "min-h-0 min-w-0 flex-1 overflow-hidden bg-lp-paper-raised",
              bothPanes && "md:w-[var(--lp-split)] md:flex-none",
            )}
          >
            <YamlEditor value={yaml} onChange={onYamlChange} label="Master resume YAML" />
          </div>
        ) : null}

        {bothPanes ? (
          <ResizeHandle
            label="Editor and preview split"
            data-testid="split-handle"
            value={splitPercent}
            min={splitMin}
            max={splitMax}
            onChange={onSplitChange}
            measure={measure}
          />
        ) : null}

        {showPreview ? (
          <div
            className={cn(
              "min-h-0 min-w-0 flex-1 overflow-hidden",
              bothPanes && "border-t border-lp-rule md:border-t-0",
            )}
          >
            <DocumentFrame
              key={previewKey}
              pdfUrl="/api/master-resume/preview"
              // The same endpoint, as a download. Section 5 requires a visible
              // download action beside the preview; the old shell offered one
              // on generated resumes only, so the master document was
              // pointer-and-sight-only.
              downloadUrl="/api/master-resume/preview"
              name="Master resume"
              testId="resume-preview"
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}
