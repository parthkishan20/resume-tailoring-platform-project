"use client";

import * as React from "react";
import { SortAscending, SortDescending } from "@phosphor-icons/react";
import { IconButton, cn } from "@/design-system";
import type { SortField, SortOrder } from "@/lib/types";

const FIELDS: { value: SortField; label: string; testId: string }[] = [
  { value: "date", label: "Date", testId: "sort-date" },
  { value: "jd", label: "Job description", testId: "sort-jd" },
];

/**
 * Sort field and direction for the library (D-45).
 *
 * DESIGN-SYSTEM.md 4.1 specifies `Select` on `@radix-ui/react-select`, and 1.4
 * did not ship it (PLAN.md 3.1: "`Select` was never needed by 2.3 and is
 * untouched"). Rather than reach for it here, on a primitive this task does
 * not own and cannot add to `design-system/`, this follows the precedent
 * `features/document/ModeSwitch.tsx` set for the same gap: a small radiogroup
 * built directly against the `lp-*` tokens. Promoting it belongs with
 * whichever task adds `@radix-ui/react-select`.
 */
export function ResumeSortControl({
  sort,
  order,
  onSortChange,
  onOrderChange,
}: {
  sort: SortField;
  order: SortOrder;
  onSortChange: (sort: SortField) => void;
  onOrderChange: (order: SortOrder) => void;
}) {
  return (
    <div className="flex items-center gap-lp-1">
      <div
        role="radiogroup"
        aria-label="Sort by"
        className={cn(
          "inline-flex items-center gap-lp-1 rounded-lp-control border border-lp-rule",
          "bg-lp-paper-sunken p-[2px]",
        )}
      >
        {FIELDS.map((field) => {
          const checked = field.value === sort;
          return (
            <button
              key={field.value}
              type="button"
              role="radio"
              aria-checked={checked}
              data-testid={field.testId}
              onClick={() => onSortChange(field.value)}
              data-lp-press=""
              className={cn(
                "h-lp-control-compact rounded-lp-control px-lp-3 font-lp-sans text-lp-label font-medium",
                "transition-transform duration-lp-press active:scale-[0.98] motion-reduce:active:scale-100",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
                checked
                  ? "bg-lp-paper-raised text-lp-ink shadow-lp-raised"
                  : "text-lp-ink-secondary hover:text-lp-ink",
              )}
            >
              {field.label}
            </button>
          );
        })}
      </div>
      <IconButton
        label={order === "desc" ? "Sort descending" : "Sort ascending"}
        icon={order === "desc" ? <SortDescending size={15} /> : <SortAscending size={15} />}
        size="sm"
        data-testid="sort-order-toggle"
        onClick={() => onOrderChange(order === "desc" ? "asc" : "desc")}
      />
    </div>
  );
}
