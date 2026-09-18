"use client";

import * as React from "react";
import { Button, cn, ErrorState, Skeleton } from "@/design-system";
import { DocumentRegion } from "@/features/document/DocumentRegion";
import { OnboardingRoute } from "@/features/onboarding/OnboardingRoute";
import { useMasterResume, useResumeList } from "@/features/queries";
import { AppearanceDialog } from "@/features/settings/AppearanceDialog";
import { AssistantPromptDialog } from "@/features/settings/AssistantPromptDialog";
import { RulesDialog } from "@/features/settings/RulesDialog";
import { Inspector, InspectorStrip } from "./Inspector";
import { NavRail, type SettingsPanel } from "./NavRail";
import { usePersistedBoolean, usePersistedNumber } from "./persist";
import { ResizeHandle } from "./ResizeHandle";
import { WorkspaceProvider } from "./WorkspaceContext";

/** DESIGN-SYSTEM.md 2.4: inspector 380px, resizable 320 to 560, persisted. */
const INSPECTOR_DEFAULT = 380;
const INSPECTOR_MIN = 320;
const INSPECTOR_MAX = 560;

/**
 * The workspace shell (DESIGN-SYSTEM.md 3.2).
 *
 * Three zones: navigation on the left with two destinations, the document
 * always in the centre, and the inspector on the right with three tabs over
 * one shared job description. It replaces a four-destination icon rail that
 * switched a single main panel, with a chat drawer overlaying the work.
 *
 * ## Responsive, which is D-43
 *
 * The old shell was `flex h-screen` over three fixed columns totalling 876px
 * of chrome before any content, and not one breakpoint prefix existed in the
 * codebase. Here:
 *
 * - Under `md` (768px) the two right zones stack: the document takes the full
 *   width at the top and the inspector is a 42dvh pane below it. The nav is a
 *   56px icon rail. Nothing is fixed-width except that rail.
 * - From `md` up, document and inspector sit side by side and the divider
 *   between them is draggable within the 320 to 560 range, persisted.
 * - From `lg` (1024px) the nav takes its 216px expanded form, subject to the
 *   user's own collapse preference, which is also persisted.
 *
 * `dvh` rather than `vh` throughout, per section 7.
 */
export function WorkspaceShell() {
  return (
    <WorkspaceProvider>
      <WorkspaceChrome />
    </WorkspaceProvider>
  );
}

function WorkspaceChrome() {
  const master = useMasterResume();
  const library = useResumeList();

  const [navCollapsed, setNavCollapsed] = usePersistedBoolean("nav-collapsed", false);
  const [inspectorCollapsed, setInspectorCollapsed] = usePersistedBoolean(
    "inspector-collapsed",
    false,
  );
  const [inspectorWidth, setInspectorWidth] = usePersistedNumber(
    "inspector-width",
    INSPECTOR_DEFAULT,
    INSPECTOR_MIN,
    INSPECTOR_MAX,
  );

  const [settings, setSettings] = React.useState<SettingsPanel | null>(null);
  const mainRef = React.useRef<HTMLDivElement>(null);

  // The inspector grows leftwards, so its width is the distance from the
  // pointer to the right edge of the region the two panes share.
  const measureInspector = React.useCallback((event: PointerEvent) => {
    const rect = mainRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return null;
    return rect.right - event.clientX;
  }, []);

  if (master.isPending) {
    return <ShellSkeleton />;
  }

  // A backend failure must never fall through to onboarding: its sample action
  // writes over whatever is actually stored (D-32).
  if (master.isError) {
    return (
      <main
        data-testid="load-error"
        className="flex min-h-[100dvh] items-center justify-center bg-lp-paper p-lp-5 font-lp-sans"
      >
        <div className="w-full max-w-[520px]">
          <ErrorState
            title="Your master resume could not be loaded"
            cause={master.error.message}
            action={
              <Button
                variant="primary"
                data-testid="load-error-retry"
                onClick={() => void master.refetch()}
                loading={master.isFetching}
                loadingLabel="Retrying"
              >
                Try again
              </Button>
            }
          />
        </div>
      </main>
    );
  }

  if (master.data === null) {
    return <OnboardingRoute />;
  }

  const masterResume = master.data;

  return (
    <div className="flex h-[100dvh] min-h-[100dvh] overflow-hidden bg-lp-paper font-lp-sans text-lp-ink">
      <NavRail
        collapsed={navCollapsed}
        onToggleCollapsed={() => setNavCollapsed(!navCollapsed)}
        onOpenSettings={setSettings}
        libraryCount={library.data?.total}
      />

      <div ref={mainRef} className="flex min-h-0 min-w-0 flex-1 flex-col md:flex-row">
        <DocumentRegion masterResume={masterResume} />

        {inspectorCollapsed ? (
          <InspectorStrip onExpand={() => setInspectorCollapsed(false)} />
        ) : (
          <>
            <ResizeHandle
              label="Document and inspector split"
              data-testid="inspector-handle"
              value={inspectorWidth}
              min={INSPECTOR_MIN}
              max={INSPECTOR_MAX}
              step={16}
              onChange={setInspectorWidth}
              measure={measureInspector}
            />
            <div
              style={{ "--lp-inspector-current": `${inspectorWidth}px` } as React.CSSProperties}
              className={cn(
                "flex h-[42dvh] min-h-0 shrink-0 flex-col",
                "md:h-auto md:w-[var(--lp-inspector-current)]",
              )}
            >
              <Inspector
                masterResume={masterResume}
                onEditRules={() => setSettings("rules")}
                onCollapse={() => setInspectorCollapsed(true)}
              />
            </div>
          </>
        )}
      </div>

      <RulesDialog
        open={settings === "rules"}
        onOpenChange={(open) => setSettings(open ? "rules" : null)}
      />
      <AssistantPromptDialog
        open={settings === "prompt"}
        onOpenChange={(open) => setSettings(open ? "prompt" : null)}
      />
      <AppearanceDialog
        open={settings === "appearance"}
        onOpenChange={(open) => setSettings(open ? "appearance" : null)}
      />
    </div>
  );
}

/**
 * Shape-matched loading, not a spinner (4.2). The three zones are drawn at
 * their real proportions and the document is a page-shaped block, so the
 * layout does not jump when the data lands.
 */
function ShellSkeleton() {
  return (
    <div
      aria-busy="true"
      className="flex h-[100dvh] min-h-[100dvh] overflow-hidden bg-lp-paper font-lp-sans"
    >
      <p aria-live="polite" className="sr-only">
        Loading your workspace
      </p>
      <div className="flex w-lp-nav-collapsed shrink-0 flex-col gap-lp-2 border-r border-lp-rule p-lp-2 lg:w-lp-nav">
        <Skeleton shape="block" className="h-lp-control" />
        <Skeleton shape="block" className="h-lp-control" />
        <Skeleton shape="block" className="h-lp-control" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col md:flex-row">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-lp-4 p-lp-4">
          <Skeleton shape="block" className="h-lp-control w-[220px]" />
          <Skeleton shape="page" className="mx-auto" />
        </div>
        <div className="flex h-[42dvh] shrink-0 flex-col gap-lp-3 border-t border-lp-rule p-lp-4 md:h-auto md:w-lp-inspector md:border-l md:border-t-0">
          <Skeleton shape="block" className="h-lp-control" />
          <Skeleton shape="block" className="h-[160px]" />
          <Skeleton shape="text" />
          <Skeleton shape="text" className="w-2/3" />
        </div>
      </div>
    </div>
  );
}
