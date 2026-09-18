"use client";

import * as React from "react";
import { useMasterResume, useSaveMasterResume } from "@/features/queries";
import type { GeneratedResume } from "@/lib/types";

/**
 * The two destinations of the new information architecture
 * (DESIGN-SYSTEM.md 3.2). Not four, and chat is not one of them.
 *
 * Deliberately a new type rather than `lib/types.ts`'s `View`, which is the
 * outgoing `"editor" | "generate" | "resumes" | "evaluate"` union. `lib/` is
 * task 2.2's, and the old union has to stay defined while the superseded
 * panels still compile against it.
 */
export type Destination = "master" | "library";

/** The three inspector tabs over one shared surface (3.2). */
export type InspectorTab = "tailor" | "evaluate" | "assistant";

export interface WorkspaceState {
  destination: Destination;
  goTo: (destination: Destination) => void;

  inspectorTab: InspectorTab;
  setInspectorTab: (tab: InspectorTab) => void;

  /**
   * THE shared job description. One string, one setter, read by the Tailor tab
   * and the Evaluate tab through the same `JobDescriptionField`.
   *
   * This is the whole of D-12. The defect was not that the old textarea was
   * styled inconsistently in two places, it was that there were two states: a
   * user who pasted a description into Generate and then opened Evaluate found
   * an empty box. There is now one place to put it and no way to introduce a
   * second, because no component below here owns job-description state.
   */
  jobDescription: string;
  setJobDescription: (value: string) => void;

  /** The generated resume the center region is showing, if any. */
  selectedResume: GeneratedResume | null;
  /**
   * Opens a generated resume in the center and switches the destination to
   * Library, which is the "generating opens the new document in the center
   * automatically" handoff in 3.2.
   */
  openResume: (resume: GeneratedResume) => void;
  clearResume: (id: number) => void;

  /**
   * The master document's live editor buffer (D-41).
   *
   * `DocumentRegion` used to own this as local state, which put it out of
   * reach of the Tailor and Evaluate tabs sitting beside it in the inspector.
   * Both must "operate on the editor's live buffer, not the last saved copy",
   * so the buffer moved up here, to the one ancestor both the document region
   * and the inspector share. `DocumentRegion` still owns the *rendering* of
   * it (the editor, the split, the save and delete affordances); this context
   * owns the buffer itself so a sibling can read it.
   *
   * `masterYaml` is always a real string: the live draft when one exists,
   * otherwise whatever the server last reported. `masterDirty` is true only
   * once the master resume has loaded and the draft differs from the server's
   * copy, so Evaluate can score it and Tailor can decide whether there is
   * anything to save before it starts.
   */
  masterYaml: string;
  masterDirty: boolean;
  setMasterDraft: (yaml: string) => void;
  /** Discards the draft, if there is one, without saving it. Used after delete. */
  discardMasterDraft: () => void;
  /** Saves the draft if there is one. A no-op, resolved immediately, if there is not. */
  saveMasterDraft: () => Promise<void>;
  masterSaving: boolean;
  masterSaveError: string | null;
}

const WorkspaceContext = React.createContext<WorkspaceState | null>(null);

/** Throws outside the provider: a silently inert nav is worse than a crash. */
export function useWorkspace(): WorkspaceState {
  const ctx = React.useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspace must be used inside a WorkspaceProvider");
  }
  return ctx;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [destination, setDestination] = React.useState<Destination>("master");
  const [inspectorTab, setInspectorTab] = React.useState<InspectorTab>("tailor");
  const [jobDescription, setJobDescription] = React.useState("");
  const [selectedResume, setSelectedResume] = React.useState<GeneratedResume | null>(null);

  const openResume = React.useCallback((resume: GeneratedResume) => {
    setSelectedResume(resume);
    setDestination("library");
  }, []);

  const clearResume = React.useCallback((id: number) => {
    setSelectedResume((current) => (current?.id === id ? null : current));
  }, []);

  // Reuses the query cache `WorkspaceShell` already populated; this does not
  // add a second fetch, only a second reader of the same entry.
  const master = useMasterResume();
  const saveMaster = useSaveMasterResume();
  const serverYaml = master.data?.yaml_content ?? "";

  // `null` means "no local edits", which is not the same as "an empty
  // document": the latter is a legitimate draft the user can save.
  const [draft, setDraft] = React.useState<string | null>(null);
  const lastServerYaml = React.useRef(serverYaml);

  React.useEffect(() => {
    if (serverYaml === lastServerYaml.current) return;
    // A server update (the assistant editing the document, a save from
    // another tab) is adopted only when there is no local edit that would be
    // lost, or when the local edit is exactly what the server now also holds
    // (P1-7: props silently overwriting state is the defect this guards).
    setDraft((current) =>
      current === null || current === lastServerYaml.current ? null : current,
    );
    lastServerYaml.current = serverYaml;
  }, [serverYaml]);

  const masterYaml = draft ?? serverYaml;
  const masterDirty = draft !== null && draft !== serverYaml;

  const setMasterDraft = React.useCallback((next: string) => setDraft(next), []);
  const discardMasterDraft = React.useCallback(() => setDraft(null), []);

  const saveMasterDraft = React.useCallback(async () => {
    if (!masterDirty) return;
    await saveMaster.mutateAsync(masterYaml);
    setDraft(null);
  }, [masterDirty, masterYaml, saveMaster]);

  // The one exit `DocumentRegion` being permanently mounted cannot cover: the
  // browser itself leaving the page. Registered only while dirty.
  React.useEffect(() => {
    if (!masterDirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      // Assigning returnValue is what actually triggers the browser's own
      // confirmation; the string is never displayed by any current browser.
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [masterDirty]);

  const masterSaveError = saveMaster.isError ? saveMaster.error.message : null;

  const value = React.useMemo<WorkspaceState>(
    () => ({
      destination,
      goTo: setDestination,
      inspectorTab,
      setInspectorTab,
      jobDescription,
      setJobDescription,
      selectedResume,
      openResume,
      clearResume,
      masterYaml,
      masterDirty,
      setMasterDraft,
      discardMasterDraft,
      saveMasterDraft,
      masterSaving: saveMaster.isPending,
      masterSaveError,
    }),
    [
      destination,
      inspectorTab,
      jobDescription,
      selectedResume,
      openResume,
      clearResume,
      masterYaml,
      masterDirty,
      setMasterDraft,
      discardMasterDraft,
      saveMasterDraft,
      saveMaster.isPending,
      masterSaveError,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
