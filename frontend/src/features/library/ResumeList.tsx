"use client";

import * as React from "react";
import { FolderOpen, Trash } from "@phosphor-icons/react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTrigger,
  EmptyState,
  ErrorState,
  IconButton,
  Skeleton,
  cn,
  useToast,
} from "@/design-system";
import {
  DEFAULT_RESUME_LIST_PARAMS,
  useDeleteResume,
  useResumeList,
  useUpdateResume,
  type ResumeListParams,
} from "@/features/queries";
import type { GeneratedResume } from "@/lib/types";
import { RenameResumeDialog } from "./RenameResumeDialog";
import { ResumePagination } from "./ResumePagination";
import { ResumeSortControl } from "./ResumeSortControl";

/**
 * The library's list column (D-45: sort order and pagination past the first
 * 20, both previously invisible even though `useResumeList` already asked the
 * API for them). Selection, opening a document, and the shell's own count all
 * stay in `WorkspaceContext`, which `LibraryDocument` wires up.
 */
export function ResumeList({
  selected,
  onSelect,
  onDeleted,
}: {
  selected: GeneratedResume | null;
  onSelect: (resume: GeneratedResume) => void;
  onDeleted: (id: number) => void;
}) {
  const { toast } = useToast();
  const [params, setParams] = React.useState<ResumeListParams>(DEFAULT_RESUME_LIST_PARAMS);
  const list = useResumeList(params);
  const remove = useDeleteResume();

  const setSort = (sort: ResumeListParams["sort"]) =>
    setParams((current) => ({ ...current, sort, page: 1 }));
  const setOrder = (order: ResumeListParams["order"]) =>
    setParams((current) => ({ ...current, order, page: 1 }));
  const setPage = (page: number) => setParams((current) => ({ ...current, page }));

  function handleDelete(resume: GeneratedResume) {
    remove.mutate(resume.id, {
      onSuccess: () => {
        onDeleted(resume.id);
        toast({ title: "Resume deleted" });
      },
    });
  }

  return (
    <div className="flex h-full w-[320px] shrink-0 flex-col border-r border-lp-rule">
      <div className="flex h-lp-panel-header shrink-0 items-center justify-between gap-lp-2 border-b border-lp-rule px-lp-4">
        <div className="flex min-w-0 items-baseline gap-lp-2">
          <h1 className="font-lp-sans text-lp-heading font-semibold text-lp-ink">Library</h1>
          {list.data ? (
            <span className="font-lp-mono text-lp-caption tabular-nums text-lp-ink-tertiary">
              {list.data.total}
            </span>
          ) : null}
        </div>
        <ResumeSortControl
          sort={params.sort}
          order={params.order}
          onSortChange={setSort}
          onOrderChange={setOrder}
        />
      </div>

      <div data-testid="resume-list" className="min-h-0 flex-1 overflow-y-auto p-lp-3">
        {list.isPending ? (
          <div className="flex flex-col gap-lp-2" aria-busy="true">
            <p aria-live="polite" className="sr-only">
              Loading the library
            </p>
            <Skeleton shape="block" className="h-[72px]" />
            <Skeleton shape="block" className="h-[72px]" />
            <Skeleton shape="block" className="h-[72px]" />
          </div>
        ) : list.isError ? (
          <ErrorState
            title="The library could not be loaded"
            cause={list.error.message}
            action={
              <button
                type="button"
                data-testid="resume-list-retry"
                onClick={() => void list.refetch()}
                className="font-lp-sans text-lp-label font-medium text-lp-accent hover:underline"
              >
                Try again
              </button>
            }
          />
        ) : list.data.items.length === 0 ? (
          <EmptyState
            icon={<FolderOpen size={22} />}
            title="No tailored resumes yet"
            description="Generate one from a job description in the Tailor tab and it will be saved here."
          />
        ) : (
          <ul className="flex flex-col gap-lp-2">
            {list.data.items.map((item) => (
              <ResumeListRow
                key={item.id}
                item={item}
                selected={selected?.id === item.id}
                onSelect={() => onSelect(item)}
                onDelete={() => handleDelete(item)}
              />
            ))}
          </ul>
        )}
      </div>

      {list.data ? (
        <ResumePagination
          page={list.data.page}
          total={list.data.total}
          limit={list.data.limit}
          onPageChange={setPage}
        />
      ) : null}
    </div>
  );
}

function ResumeListRow({
  item,
  selected,
  onSelect,
  onDelete,
}: {
  item: GeneratedResume;
  selected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const { toast } = useToast();
  const rename = useUpdateResume(item.id);

  return (
    <li>
      <div
        data-testid="resume-list-item"
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect();
          }
        }}
        className={cn(
          "group flex cursor-pointer flex-col gap-lp-1 rounded-lp-surface border p-lp-3 text-left",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
          selected
            ? "border-lp-accent bg-lp-accent-wash"
            : "border-lp-rule bg-lp-paper-raised hover:border-lp-rule-strong hover:bg-lp-paper-sunken",
        )}
      >
        <div className="flex items-start justify-between gap-lp-2">
          <p
            data-testid="resume-name"
            className="min-w-0 flex-1 truncate font-lp-sans text-lp-label font-medium text-lp-ink"
          >
            {item.name}
          </p>
          <div className="flex shrink-0 items-center gap-lp-1 opacity-0 focus-within:opacity-100 group-hover:opacity-100">
            <RenameResumeDialog
              name={item.name}
              pending={rename.isPending}
              testId="rename-resume"
              onRename={(name) => {
                rename.mutate(
                  { name },
                  { onSuccess: () => toast({ title: "Resume renamed", tone: "positive" }) },
                );
              }}
            />
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <IconButton
                  label={`Delete ${item.name}`}
                  icon={<Trash size={14} />}
                  size="sm"
                  data-testid="delete-resume"
                  onClick={(event) => event.stopPropagation()}
                />
              </AlertDialogTrigger>
              <AlertDialogContent
                title="Delete this resume?"
                description="This removes the tailored resume and its rendered PDF. This cannot be undone."
                confirmLabel="Delete"
                onConfirm={onDelete}
              />
            </AlertDialog>
          </div>
        </div>
        <p className="truncate text-lp-caption text-lp-ink-tertiary">
          {item.job_description.slice(0, 80)}
        </p>
        <span className="font-lp-mono text-lp-caption tabular-nums text-lp-ink-tertiary">
          {new Date(item.created_at).toLocaleDateString()}
        </span>
      </div>
    </li>
  );
}
