"use client";

import * as React from "react";
import { FolderOpen } from "@phosphor-icons/react";
import { EmptyState } from "@/design-system";
import { useInvalidateResumes } from "@/features/queries";
import { useWorkspace } from "@/features/workspace/WorkspaceContext";
import { GeneratedResumeDocument } from "./GeneratedResumeDocument";
import { ResumeList } from "./ResumeList";

/**
 * The Library destination (D-45): a list beside a document, the same shape
 * the center region uses everywhere else. `ResumeList` owns sorting,
 * pagination, rename and delete; `GeneratedResumeDocument` owns editing and
 * re-rendering the selected one, mirroring `MasterDocument`'s Editor / Split /
 * Preview control per DESIGN-SYSTEM.md 3.2.
 *
 * What this wrapper adds is the part that is information architecture rather
 * than feature logic: selection is lifted into the workspace, so "generating
 * opens the new document in the center automatically" (DESIGN-SYSTEM.md 3.2)
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
    <section aria-label="Library" className="flex h-full min-w-0 bg-lp-paper">
      <ResumeList selected={selectedResume} onSelect={openResume} onDeleted={handleDeleted} />
      <div className="min-h-0 min-w-0 flex-1">
        {selectedResume ? (
          <GeneratedResumeDocument key={selectedResume.id} summary={selectedResume} />
        ) : (
          <div className="flex h-full items-center justify-center p-lp-8">
            <EmptyState
              icon={<FolderOpen size={22} />}
              title="Select a resume"
              description="Choose a tailored resume from the list to view, edit or re-render it."
            />
          </div>
        )}
      </div>
    </section>
  );
}
