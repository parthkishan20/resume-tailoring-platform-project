"use client";

import * as React from "react";
import { useToast } from "@/design-system";
import { LibraryDocument } from "@/features/library/LibraryDocument";
import { useDeleteMasterResume } from "@/features/queries";
import { usePersistedNumber } from "@/features/workspace/persist";
import { useWorkspace } from "@/features/workspace/WorkspaceContext";
import type { MasterResume } from "@/lib/types";
import type { DocumentMode } from "@/design-system";
import { MasterDocument } from "./MasterDocument";

export const SPLIT_MIN = 25;
export const SPLIT_MAX = 75;
const SPLIT_DEFAULT = 50;

export interface DocumentRegionProps {
  masterResume: MasterResume;
}

/**
 * The centre region, and the owner of everything that must survive navigation.
 *
 * ## D-30, the worst bug in the app
 *
 * The old shell put the YAML buffer in `MasterResumePanel`'s local state and
 * then conditionally rendered that panel from the nav. Clicking any other nav
 * item unmounted the panel and threw the buffer away, with the header still
 * reading "edited" as it went. There was no guard of any kind.
 *
 * The fix here is structural rather than a warning bolted onto the old shape:
 * the buffer lives in this component, which the shell mounts once and never
 * unmounts, and `MasterDocument` is fully controlled. Switching destination
 * between Master and Library, switching inspector tab, resizing, changing
 * theme, generating a resume: none of them can reach the draft, because none
 * of them unmount its owner. There is no in-app path left that discards it.
 *
 * A dirty guard is still the right answer for the one exit this cannot cover,
 * which is the browser leaving the page, so `beforeunload` is registered while
 * and only while the draft differs from what the server holds. Both halves of
 * task 0.3 are therefore closed here.
 *
 * ## P1-7, props-to-state desync
 *
 * A consequence of the same inversion, so it is fixed rather than reproduced.
 * Server content is adopted into the draft only when the user has not edited,
 * or when their draft matches what the server previously held. If the
 * assistant rewrites the master resume while there are unsaved edits on
 * screen, the edits win and stay on screen; the old panel's `useState`
 * initialiser silently ignored the new prop instead.
 *
 * ## The buffer itself moved, in task 3.1
 *
 * The draft, the dirty flag and the save action used to be local state here.
 * They now live in `WorkspaceContext` (`masterYaml`/`masterDirty`/
 * `setMasterDraft`/`saveMasterDraft`), because Tailor and Evaluate, mounted as
 * siblings in the inspector rather than descendants of this component, need
 * the same live buffer to satisfy D-41 ("operate on the editor's live buffer,
 * not the last saved copy"). This component still owns everything about
 * *rendering* the buffer: the editor, the split, the save button, delete.
 */
export function DocumentRegion({ masterResume }: DocumentRegionProps) {
  const {
    destination,
    masterYaml,
    masterDirty,
    setMasterDraft,
    discardMasterDraft,
    saveMasterDraft,
    masterSaving,
    masterSaveError,
  } = useWorkspace();
  const { toast } = useToast();

  const [mode, setMode] = React.useState<DocumentMode>("split");
  const [splitPercent, setSplitPercent] = usePersistedNumber(
    "split",
    SPLIT_DEFAULT,
    SPLIT_MIN,
    SPLIT_MAX,
  );
  const [previewKey, setPreviewKey] = React.useState(0);

  const remove = useDeleteMasterResume();

  const handleSave = React.useCallback(() => {
    if (masterSaving || !masterDirty) return;
    saveMasterDraft()
      .then(() => {
        setPreviewKey((key) => key + 1);
        toast({ title: "Master resume saved", tone: "positive" });
      })
      .catch(() => {
        // `masterSaveError` from context already renders the banner below.
      });
  }, [masterSaving, masterDirty, saveMasterDraft, toast]);

  const handleDelete = React.useCallback(() => {
    remove.mutate(undefined, {
      onSuccess: () => {
        discardMasterDraft();
        toast({ title: "Master resume deleted" });
      },
    });
  }, [remove, discardMasterDraft, toast]);

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {destination === "master" ? (
        <MasterDocument
          yaml={masterYaml}
          onYamlChange={setMasterDraft}
          dirty={masterDirty}
          updatedAt={masterResume.updated_at}
          mode={mode}
          onModeChange={setMode}
          splitPercent={splitPercent}
          onSplitChange={setSplitPercent}
          splitMin={SPLIT_MIN}
          splitMax={SPLIT_MAX}
          onSave={handleSave}
          saving={masterSaving}
          saveError={masterSaveError}
          onDelete={handleDelete}
          previewKey={previewKey}
        />
      ) : (
        <LibraryDocument />
      )}
    </div>
  );
}
