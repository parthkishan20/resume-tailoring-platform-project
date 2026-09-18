"use client";

import * as React from "react";
import { SidebarSimple } from "@phosphor-icons/react";
import { cn, IconButton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/design-system";
import { AssistantPanel } from "@/features/assistant/AssistantPanel";
import { EvaluatePanel } from "@/features/evaluate/EvaluatePanel";
import { TailorPanel } from "@/features/tailor/TailorPanel";
import type { MasterResume } from "@/lib/types";
import { useWorkspace, type InspectorTab } from "./WorkspaceContext";

const TABS: { value: InspectorTab; label: string }[] = [
  { value: "tailor", label: "Tailor" },
  { value: "evaluate", label: "Evaluate" },
  { value: "assistant", label: "Assistant" },
];

export interface InspectorProps {
  masterResume: MasterResume;
  onEditRules: () => void;
  onCollapse: () => void;
}

/**
 * The right rail (DESIGN-SYSTEM.md 3.2): three tabs over one shared surface.
 *
 * `forceMount` on every panel is load bearing, not a detail. Radix unmounts an
 * inactive tab panel by default, and unmounting the Assistant would refetch
 * the whole conversation on every tab switch, which is precisely the cost the
 * audit measured on the old chat drawer (P1-20). Mounted panels also mean a
 * run started under Tailor keeps streaming while the user reads Evaluate.
 *
 * Radix supplies the roving-tabindex contract the hand-rolled `role="tab"`
 * markup never had (D-44): one tab stop for the list, arrows to move, Home
 * and End to the ends.
 */
export function Inspector({ masterResume, onEditRules, onCollapse }: InspectorProps) {
  const { inspectorTab, setInspectorTab } = useWorkspace();

  return (
    <aside
      aria-label="Inspector"
      data-testid="inspector"
      className={cn(
        "flex h-full min-h-0 w-full min-w-0 flex-col",
        "border-t border-lp-rule bg-lp-paper-sunken md:border-l md:border-t-0",
      )}
    >
      <Tabs
        value={inspectorTab}
        onValueChange={(next) => setInspectorTab(next as InspectorTab)}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="flex shrink-0 items-stretch border-b border-lp-rule bg-lp-paper-sunken">
          <TabsList className="min-w-0 flex-1 !border-b-0">
            {TABS.map((tab) => (
              <TabsTrigger
                key={tab.value}
                value={tab.value}
                data-testid={`inspector-tab-${tab.value}`}
              >
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <div className="hidden shrink-0 items-center px-lp-2 md:flex">
            <IconButton
              label="Collapse inspector"
              icon={<SidebarSimple size={16} />}
              size="sm"
              tooltipSide="left"
              data-testid="inspector-collapse"
              onClick={onCollapse}
            />
          </div>
        </div>

        <TabsContent
          value="tailor"
          forceMount
          className="min-h-0 flex-1 overflow-y-auto data-[state=inactive]:hidden"
        >
          <TailorPanel onEditRules={onEditRules} />
        </TabsContent>
        <TabsContent
          value="evaluate"
          forceMount
          className="min-h-0 flex-1 overflow-y-auto data-[state=inactive]:hidden"
        >
          <EvaluatePanel masterResume={masterResume} />
        </TabsContent>
        <TabsContent
          value="assistant"
          forceMount
          className="min-h-0 flex-1 overflow-hidden !p-0 data-[state=inactive]:hidden"
        >
          <AssistantPanel masterResume={masterResume} />
        </TabsContent>
      </Tabs>
    </aside>
  );
}

/**
 * What is left of the inspector once it is collapsed: a strip carrying the one
 * control that brings it back. `md` and above only, matching the aside above.
 */
export function InspectorStrip({ onExpand }: { onExpand: () => void }) {
  return (
    <div
      data-testid="inspector-strip"
      className="hidden shrink-0 flex-col items-center gap-lp-2 border-l border-lp-rule bg-lp-paper px-lp-2 py-lp-3 md:flex"
    >
      <IconButton
        label="Expand inspector"
        icon={<SidebarSimple size={16} />}
        size="sm"
        tooltipSide="left"
        data-testid="inspector-expand"
        onClick={onExpand}
      />
    </div>
  );
}
