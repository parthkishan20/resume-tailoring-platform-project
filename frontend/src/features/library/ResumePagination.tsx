"use client";

import * as React from "react";
import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { IconButton } from "@/design-system";

/** Page controls for `GET /api/resumes` (D-45: pagination past the first 20). */
export function ResumePagination({
  page,
  total,
  limit,
  onPageChange,
}: {
  page: number;
  total: number;
  limit: number;
  onPageChange: (page: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / limit));

  if (pageCount <= 1) return null;

  return (
    <div
      className="flex shrink-0 items-center justify-between gap-lp-2 border-t border-lp-rule px-lp-3 py-lp-2"
      aria-label="Library pages"
    >
      <IconButton
        label="Previous page"
        icon={<CaretLeft size={14} />}
        size="sm"
        data-testid="library-page-prev"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      />
      <span
        data-testid="library-page-status"
        className="font-lp-mono text-lp-caption tabular-nums text-lp-ink-tertiary"
      >
        Page {page} of {pageCount}
      </span>
      <IconButton
        label="Next page"
        icon={<CaretRight size={14} />}
        size="sm"
        data-testid="library-page-next"
        disabled={page >= pageCount}
        onClick={() => onPageChange(page + 1)}
      />
    </div>
  );
}
