"use client";
import { useState, useEffect, useCallback } from "react";
import Sidebar from "./Sidebar";
import EmptyState from "./EmptyState";
import MasterResumePanel from "./MasterResumePanel";
import GenerationPanel from "./GenerationPanel";
import ResumeListPanel from "./ResumeListPanel";
import EvaluationPanel from "./EvaluationPanel";
import ChatDrawer from "./ChatDrawer";
import Spinner from "./ui/Spinner";
import Button from "./ui/Button";
import type { MasterResume, GeneratedResume, View } from "@/lib/types";
import { api } from "@/lib/api";

export default function WorkstationShell() {
  const [masterResume, setMasterResume] = useState<MasterResume | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<View>("editor");
  const [selectedResume, setSelectedResume] = useState<GeneratedResume | null>(null);
  const [chatOpen, setChatOpen] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    api.getMasterResume()
      .then((r) => setMasterResume(r))
      .catch((e: unknown) =>
        setLoadError(e instanceof Error ? e.message : "Could not reach the server")
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleImport = useCallback((r: MasterResume) => setMasterResume(r), []);
  const handleLoadSample = useCallback(async (yaml: string) => {
    // Persist immediately so preview/generation/delete work without a manual save
    const saved = await api.saveMasterResume(yaml);
    setMasterResume(saved);
  }, []);
  const handleResumeDeleted = useCallback((id: number) => {
    setSelectedResume((s) => (s?.id === id ? null : s));
  }, []);
  const handleGenerated = useCallback((r: GeneratedResume) => setSelectedResume(r), []);
  const handleMasterDeleted = useCallback(() => {
    setMasterResume(null);
    setView("editor");
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <span className="font-display text-3xl italic text-foreground">
          Resume<span className="text-accent">Tailor</span>
        </span>
        <Spinner className="text-accent" />
      </div>
    );
  }

  // A backend failure must never fall through to onboarding: its sample button overwrites data.
  if (loadError) {
    return (
      <div
        className="flex h-screen flex-col items-center justify-center gap-4 px-6 text-center"
        data-testid="load-error"
      >
        <span className="font-display text-3xl italic text-foreground">
          Resume<span className="text-accent">Tailor</span>
        </span>
        <div role="alert" className="max-w-md">
          <p className="text-sm text-foreground">We could not load your master resume.</p>
          <p className="mt-1 text-xs text-error">{loadError}</p>
        </div>
        <Button variant="primary" onClick={load} data-testid="load-error-retry">
          Try again
        </Button>
      </div>
    );
  }

  if (!masterResume) {
    return <EmptyState onImport={handleImport} onLoadSample={handleLoadSample} />;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        view={view}
        onNavigate={setView}
        chatOpen={chatOpen}
        onToggleChat={() => setChatOpen((o) => !o)}
      />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {view === "editor" && (
          <MasterResumePanel
            resume={masterResume}
            onSave={setMasterResume}
            onDelete={handleMasterDeleted}
          />
        )}
        {view === "generate" && (
          <GenerationPanel masterResume={masterResume} onGenerated={handleGenerated} />
        )}
        {view === "resumes" && (
          <ResumeListPanel
            selected={selectedResume}
            onSelect={setSelectedResume}
            onDeleted={handleResumeDeleted}
          />
        )}
        {view === "evaluate" && <EvaluationPanel masterResume={masterResume} />}
      </main>
      {chatOpen && (
        <ChatDrawer
          masterResume={masterResume}
          onAction={setMasterResume}
          onClose={() => setChatOpen(false)}
        />
      )}
    </div>
  );
}
