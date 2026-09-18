"use client";

import * as React from "react";
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
    }),
    [destination, inspectorTab, jobDescription, selectedResume, openResume, clearResume],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
