"use client";

import * as React from "react";
import {
  Books,
  ChatText,
  FileText,
  Palette,
  SidebarSimple,
  Sliders,
  type Icon,
} from "@phosphor-icons/react";
import { cn, Tooltip } from "@/design-system";
import { useWorkspace, type Destination } from "./WorkspaceContext";

export type SettingsPanel = "rules" | "prompt" | "appearance";

interface NavRailProps {
  /** The user's explicit choice. Only honoured at `lg` and above. */
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onOpenSettings: (panel: SettingsPanel) => void;
  /** Library size, from the shell's own query. Undefined while it loads. */
  libraryCount: number | undefined;
}

interface DestinationEntry {
  destination: Destination;
  label: string;
  icon: Icon;
  testId: string;
}

const DESTINATIONS: DestinationEntry[] = [
  { destination: "master", label: "Master", icon: FileText, testId: "nav-master" },
  { destination: "library", label: "Library", icon: Books, testId: "nav-library" },
];

interface SettingsEntry {
  panel: SettingsPanel;
  label: string;
  icon: Icon;
  testId: string;
}

const SETTINGS: SettingsEntry[] = [
  { panel: "rules", label: "Generation rules", icon: Sliders, testId: "nav-rules" },
  { panel: "prompt", label: "Assistant prompt", icon: ChatText, testId: "nav-prompt" },
  { panel: "appearance", label: "Appearance", icon: Palette, testId: "nav-appearance" },
];

/**
 * One row of the rail.
 *
 * Collapse is expressed in CSS, not in JavaScript. A `useMediaQuery` would
 * have to render one layout on the server and possibly another on the client,
 * which is either a hydration mismatch or a visible jump on every load; the
 * breakpoint variants below have neither problem, and `lg:` picks up the
 * user's persisted choice only at the width where 216px of rail is affordable.
 *
 * The label is therefore always in the DOM and hidden by the `expanded`
 * classes, the accessible name always comes from `aria-label` rather than from
 * whichever of the two is currently visible, and the tooltip is always
 * attached because at every width narrower than `lg` this row is an icon with
 * no text beside it (DESIGN-SYSTEM.md 3.2, section 5).
 */
function NavRow({
  label,
  icon: IconComponent,
  expanded,
  active,
  trailing,
  testId,
  onClick,
}: {
  label: string;
  icon: Icon;
  /** Whether the label may show at `lg` and above. */
  expanded: boolean;
  active?: boolean;
  trailing?: React.ReactNode;
  testId: string;
  onClick: () => void;
}) {
  return (
    <Tooltip label={label} side="right">
      <button
        type="button"
        data-testid={testId}
        onClick={onClick}
        aria-label={label}
        aria-current={active ? "page" : undefined}
        data-lp-press=""
        className={cn(
          "flex h-lp-control w-full items-center justify-center rounded-lp-control",
          "font-lp-sans text-lp-label font-medium",
          "transition-transform duration-lp-press active:scale-[0.98] motion-reduce:active:scale-100",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
          active
            ? "bg-lp-accent-wash text-lp-accent"
            : "text-lp-ink-secondary hover:bg-lp-paper-sunken hover:text-lp-ink",
          expanded && "lg:justify-start lg:gap-lp-3 lg:px-lp-2",
        )}
      >
        <IconComponent
          size={18}
          weight={active ? "fill" : "regular"}
          aria-hidden="true"
          className="shrink-0"
        />
        <span
          aria-hidden="true"
          className={cn("hidden min-w-0 flex-1 truncate text-left", expanded && "lg:block")}
        >
          {label}
        </span>
        {trailing !== undefined ? (
          <span className={cn("hidden shrink-0", expanded && "lg:block")}>{trailing}</span>
        ) : null}
      </button>
    </Tooltip>
  );
}

/**
 * Left navigation (DESIGN-SYSTEM.md 3.2): two destinations, then a divider,
 * then three settings entries that open dialogs rather than replacing the
 * workspace. 216px expanded and 56px collapsed, per 2.4.
 *
 * This is the half of D-43 that the old rail got wrong at every width: 76px of
 * unlabelled icons with 10px captions under them, four destinations one of
 * which was not a destination, and no breakpoint anywhere.
 */
export function NavRail({
  collapsed,
  onToggleCollapsed,
  onOpenSettings,
  libraryCount,
}: NavRailProps) {
  const { destination, goTo } = useWorkspace();
  const expanded = !collapsed;

  return (
    <nav
      aria-label="Workspace"
      data-testid="nav-rail"
      className={cn(
        "flex h-full shrink-0 flex-col gap-lp-4 border-r border-lp-rule bg-lp-paper px-lp-2 py-lp-3",
        "w-lp-nav-collapsed",
        expanded && "lg:w-lp-nav",
      )}
    >
      <div
        className={cn("flex h-lp-control items-center justify-center", expanded && "lg:px-lp-2")}
      >
        <span
          className={cn(
            "hidden min-w-0 flex-1 truncate font-lp-sans text-lp-label font-semibold text-lp-ink",
            expanded && "lg:block",
          )}
        >
          ResumeTailor
        </span>
        <Tooltip label={collapsed ? "Expand navigation" : "Collapse navigation"} side="right">
          <button
            type="button"
            data-testid="nav-collapse-toggle"
            onClick={onToggleCollapsed}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            aria-expanded={expanded}
            className={cn(
              "hidden h-lp-control w-lp-control shrink-0 items-center justify-center rounded-lp-control lg:inline-flex",
              "text-lp-ink-secondary hover:bg-lp-paper-sunken hover:text-lp-ink",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
            )}
          >
            <SidebarSimple size={18} aria-hidden="true" />
          </button>
        </Tooltip>
      </div>

      <ul className="flex flex-col gap-lp-1">
        {DESTINATIONS.map((entry) => (
          <li key={entry.destination}>
            <NavRow
              label={entry.label}
              icon={entry.icon}
              expanded={expanded}
              active={destination === entry.destination}
              testId={entry.testId}
              onClick={() => goTo(entry.destination)}
              trailing={
                entry.destination === "library" && libraryCount !== undefined ? (
                  <span className="font-lp-mono text-lp-caption tabular-nums text-lp-ink-tertiary">
                    {libraryCount}
                  </span>
                ) : undefined
              }
            />
          </li>
        ))}
      </ul>

      <div className="mt-auto flex flex-col gap-lp-1">
        <hr className="mb-lp-1 border-0 border-t border-lp-rule" />
        {SETTINGS.map((entry) => (
          <NavRow
            key={entry.panel}
            label={entry.label}
            icon={entry.icon}
            expanded={expanded}
            testId={entry.testId}
            onClick={() => onOpenSettings(entry.panel)}
          />
        ))}
      </div>
    </nav>
  );
}
