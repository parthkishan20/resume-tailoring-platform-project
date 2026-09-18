"use client";

import * as React from "react";
import ResumeListPanel from "@/components/ResumeListPanel";
import { useWorkspace } from "@/features/workspace/WorkspaceContext";
import { useInvalidateResumes } from "@/features/queries";

/**
 * The Library destination.
 *
 * `ResumeListPanel` is re-hosted verbatim: it is already a list beside a
 * preview, which is a centre-region shape, and its internals (rename, edit,
 * re-render, sort order, pagination) are task 3.2's.
 *
 * What this wrapper adds is the part that is information architecture rather
 * than feature logic: selection is lifted into the workspace, so "generating
 * opens the new document in the centre automatically" (DESIGN-SYSTEM.md 3.2)
 * has somewhere to put the result, and a delete invalidates the shell's own
 * library query so the nav count and the list cannot disagree.
 */
export function LibraryDocument() {
  const { selectedResume, openResume, clearResume } = useWorkspace();
  const invalidateResumes = useInvalidateResumes();

  const handleDeleted = React.useCallback(
    (id: number) => {
      clearResume(id);
      invalidateResumes();
    },
    [clearResume, invalidateResumes],
  );

  return (
    <section aria-label="Library" className="flex h-full min-w-0 flex-col bg-lp-paper">
      <ResumeListPanel selected={selectedResume} onSelect={openResume} onDeleted={handleDeleted} />
    </section>
  );
}
