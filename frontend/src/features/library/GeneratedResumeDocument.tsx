"use client";

import * as React from "react";
import { ArrowsClockwise, FloppyDisk, Trash } from "@phosphor-icons/react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTrigger,
  Button,
  cn,
  DocumentFrame,
  ErrorState,
  ModeSwitch,
  Skeleton,
  useToast,
  type DocumentMode,
} from "@/design-system";
import { YamlEditor } from "@/features/document/YamlEditor";
import { useDeleteResume, useRenderResume, useResume, useUpdateResume } from "@/features/queries";
import { ResizeHandle } from "@/features/workspace/ResizeHandle";
import { useWorkspace } from "@/features/workspace/WorkspaceContext";
import { api } from "@/lib/api";
import type { GeneratedResume } from "@/lib/types";
import { RenameResumeDialog } from "./RenameResumeDialog";

const SPLIT_MIN = 25;
const SPLIT_MAX = 75;
const SPLIT_DEFAULT = 50;

/**
 * A generated resume as a document (D-45: edit, re-render, rename), the
 * generated-resume half of the "same three-mode control whether the document
 * is the master resume or a generated one" DESIGN-SYSTEM.md 3.2 asks for.
 *
 * Deliberately simpler than `MasterDocument`'s dirty tracking: nothing in the
 * product today edits a stored generated resume's YAML from outside this
 * component (the assistant's four tools operate on the master resume and on
 * creating new generated resumes, not on rewriting one in place), so there is
 * no P1-7-shaped race to guard against here. A local draft that is dropped
 * whenever the server row changes underneath it is the right amount of
 * complexity for what actually happens today; that assumption is the first
 * thing to revisit if a future tool starts editing generated resumes too.
 *
 * The PDF and the YAML are independent on this document, unlike the master's
 * live preview: `PATCH` validates and stores YAML but does not render (D-04),
 * so the preview keeps showing the last rendered PDF until "Re-render" is
 * pressed. That is a real property of the backend, not a bug, and D-45 lists
 * it as its own capability.
 */
export function GeneratedResumeDocument({ summary }: { summary: GeneratedResume }) {
  const { toast } = useToast();
  const { clearResume } = useWorkspace();
  const detail = useResume(summary.id);

  const [mode, setMode] = React.useState<DocumentMode>("split");
  const [splitPercent, setSplitPercent] = React.useState(SPLIT_DEFAULT);
  const [yamlDraft, setYamlDraft] = React.useState<string | null>(null);
  const [previewKey, setPreviewKey] = React.useState(0);
  const splitRef = React.useRef<HTMLDivElement>(null);

  const resume = detail.data;
  const savedYaml = resume?.yaml_content ?? "";
  const lastSavedYaml = React.useRef(savedYaml);

  React.useEffect(() => {
    if (savedYaml === lastSavedYaml.current) return;
    setYamlDraft(null);
    lastSavedYaml.current = savedYaml;
  }, [savedYaml]);

  const yaml = yamlDraft ?? savedYaml;
  const dirty = yamlDraft !== null && yamlDraft !== savedYaml;

  const update = useUpdateResume(summary.id);
  const render = useRenderResume(summary.id);
  const remove = useDeleteResume();
  const rename = useUpdateResume(summary.id);

  const handleSave = React.useCallback(() => {
    if (update.isPending || !dirty) return;
    update.mutate(
      { yaml_content: yaml },
      {
        onSuccess: () => {
          setYamlDraft(null);
          toast({
            title: "Resume saved",
            tone: "positive",
            description: "Re-render to update the PDF preview.",
          });
        },
      },
    );
  }, [update, dirty, yaml, toast]);

  const handleRender = React.useCallback(() => {
    render.mutate(undefined, {
      onSuccess: () => {
        setPreviewKey((key) => key + 1);
        toast({ title: "Resume re-rendered", tone: "positive" });
      },
    });
  }, [render, toast]);

  const handleDelete = React.useCallback(() => {
    remove.mutate(summary.id, {
      onSuccess: () => {
        clearResume(summary.id);
        toast({ title: "Resume deleted" });
      },
    });
  }, [remove, summary.id, clearResume, toast]);

  const measure = React.useCallback((event: PointerEvent) => {
    const rect = splitRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return null;
    return ((event.clientX - rect.left) / rect.width) * 100;
  }, []);

  if (detail.isPending) {
    return (
      <div className="flex h-full flex-col gap-lp-4 p-lp-4" aria-busy="true">
        <Skeleton shape="text" className="w-1/3" />
        <Skeleton shape="page" />
      </div>
    );
  }

  if (detail.isError) {
    return (
      <div className="p-lp-4">
        <ErrorState
          title="The resume could not be loaded"
          cause={detail.error.message}
          action={
            <Button variant="secondary" size="sm" onClick={() => void detail.refetch()}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  if (!resume) return null;

  const name = resume.name;
  const showEditor = mode !== "preview";
  const showPreview = mode !== "editor";
  const bothPanes = showEditor && showPreview;
  const saveError = update.isError ? update.error.message : null;

  return (
    <section aria-label={`Resume: ${name}`} className="flex h-full min-w-0 flex-col">
      <header
        className={cn(
          "flex shrink-0 flex-col gap-lp-2 border-b border-lp-rule bg-lp-paper px-lp-4 py-lp-2",
          "lg:h-lp-panel-header lg:flex-row lg:items-center lg:justify-between lg:gap-lp-3 lg:py-0",
        )}
      >
        <div className="flex min-w-0 items-center gap-lp-2">
          <h1 className="truncate font-lp-sans text-lp-title font-semibold text-lp-ink">{name}</h1>
          <RenameResumeDialog
            name={name}
            pending={rename.isPending}
            testId="rename-open-resume"
            onRename={(nextName) => {
              rename.mutate(
                { name: nextName },
                { onSuccess: () => toast({ title: "Resume renamed", tone: "positive" }) },
              );
            }}
          />
          <span className="truncate font-lp-mono text-lp-caption tabular-nums text-lp-ink-tertiary">
            {dirty ? "Unsaved edits" : `Saved ${new Date(resume.updated_at).toLocaleString()}`}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-lp-2 lg:shrink-0">
          <ModeSwitch value={mode} onChange={setMode} />
          <Button
            data-testid="save-resume"
            variant="primary"
            size="sm"
            icon={<FloppyDisk size={15} />}
            onClick={handleSave}
            loading={update.isPending}
            loadingLabel="Saving"
            disabled={!dirty}
          >
            Save
          </Button>
          <Button
            data-testid="render-resume"
            variant="secondary"
            size="sm"
            icon={<ArrowsClockwise size={15} />}
            onClick={handleRender}
            loading={render.isPending}
            loadingLabel="Rendering"
          >
            Re-render
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                data-testid="delete-resume-document"
                variant="ghost"
                size="sm"
                icon={<Trash size={15} />}
              >
                Delete
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent
              title="Delete this resume?"
              description="This removes the tailored resume and its rendered PDF. This cannot be undone."
              confirmLabel="Delete"
              onConfirm={handleDelete}
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
              <Button variant="secondary" size="sm" onClick={handleSave}>
                Try again
              </Button>
            }
          />
        </div>
      ) : null}

      <div ref={splitRef} className="flex min-h-0 flex-1 flex-col md:flex-row">
        {showEditor ? (
          <div
            data-testid="resume-yaml-editor"
            style={{ "--lp-split": `${splitPercent}%` } as React.CSSProperties}
            className={cn(
              "min-h-0 min-w-0 flex-1 overflow-hidden bg-lp-paper-raised",
              bothPanes && "md:w-[var(--lp-split)] md:flex-none",
            )}
          >
            <YamlEditor value={yaml} onChange={setYamlDraft} label={`${name} YAML`} />
          </div>
        ) : null}

        {bothPanes ? (
          <ResizeHandle
            label="Editor and preview split"
            data-testid="resume-split-handle"
            value={splitPercent}
            min={SPLIT_MIN}
            max={SPLIT_MAX}
            onChange={setSplitPercent}
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
              pdfUrl={api.getPdfUrl(summary.id)}
              downloadUrl={api.getPdfUrl(summary.id)}
              name={name}
              testId="generated-resume-preview"
            />
          </div>
        ) : null}
      </div>
    </section>
  );
}
