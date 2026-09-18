"use client";

import * as React from "react";
import { Desktop, Moon, Sun, type Icon } from "@phosphor-icons/react";
import { useTheme } from "next-themes";
import { cn, Dialog, DialogContent } from "@/design-system";

const CHOICES: { value: string; label: string; icon: Icon; hint: string }[] = [
  { value: "light", label: "Light", icon: Sun, hint: "The base definition." },
  { value: "dark", label: "Dark", icon: Moon, hint: "A full token swap." },
  { value: "system", label: "System", icon: Desktop, hint: "Follow the operating system." },
];

/**
 * Appearance (DESIGN-SYSTEM.md 3.2, decision D2).
 *
 * This is the control that closes D-11. `next-themes` has been a dependency
 * that nothing imported since the app shipped, while `layout.tsx` hardcoded
 * `className="dark"`; task 1.4 wired the provider and the token swap, and this
 * is the switch. Light is the default, the system preference is respected, and
 * the choice is `next-themes`' own persistence rather than a second store.
 *
 * It is the only appearance control in the product. A quick toggle in the nav
 * as well would be a second control for one intent, which section 7 forbids.
 *
 * The selected value is `undefined` until the client has read storage, so the
 * group renders with nothing selected on the server and settles after mount.
 * Reading it during render is the hydration mismatch the old `/design` route
 * already had to work around.
 */
export function AppearanceDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => setMounted(true), []);

  const selected = mounted ? theme : undefined;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Appearance"
        description="Light is the default. Dark is a full token swap, not a filter."
      >
        <div role="radiogroup" aria-label="Theme" className="flex flex-col gap-lp-2">
          {CHOICES.map((choice) => {
            const checked = selected === choice.value;
            return (
              <button
                key={choice.value}
                type="button"
                role="radio"
                aria-checked={checked}
                data-testid={`theme-${choice.value}`}
                onClick={() => setTheme(choice.value)}
                data-lp-press=""
                className={cn(
                  "flex items-center gap-lp-3 rounded-lp-control border px-lp-3 py-lp-2 text-left",
                  "font-lp-sans transition-transform duration-lp-press active:scale-[0.98]",
                  "motion-reduce:active:scale-100",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
                  checked
                    ? "border-lp-accent-edge bg-lp-accent-wash"
                    : "border-lp-rule bg-lp-paper-raised hover:border-lp-rule-strong",
                )}
              >
                <choice.icon
                  size={18}
                  aria-hidden="true"
                  className={cn("shrink-0", checked ? "text-lp-accent" : "text-lp-ink-secondary")}
                />
                <span className="flex min-w-0 flex-col">
                  <span
                    className={cn(
                      "text-lp-label font-medium",
                      checked ? "text-lp-accent" : "text-lp-ink",
                    )}
                  >
                    {choice.label}
                  </span>
                  <span className="text-lp-caption text-lp-ink-tertiary">{choice.hint}</span>
                </span>
              </button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
