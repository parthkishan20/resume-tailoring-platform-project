"use client";

import * as React from "react";
import { DownloadSimple } from "@phosphor-icons/react";
import PdfPreview from "@/components/PdfPreview";
import { cn } from "@/design-system";

export interface DocumentFrameProps {
  /** Where the rendered PDF is fetched from. */
  pdfUrl: string;
  /** Where the same PDF is downloaded from. Omitted for the live preview. */
  downloadUrl?: string;
  /** Names the document in the download affordance and the iframe title. */
  name: string;
  testId?: string;
}

/**
 * The paper sheet (DESIGN-SYSTEM.md 4.1, 2.5).
 *
 * `--shadow-page` is used on exactly one element in the product and this is
 * it: the rendered document is the one object that should read as a physical
 * sheet. The accent is banned inside this frame, per 2.1, so the chrome around
 * the sheet is neutral and nothing here is cobalt.
 *
 * `PdfPreview` is re-hosted unchanged. It owns the fetch-to-blob pipeline and
 * the `<iframe title>` that section 5 requires, and its internals belong to a
 * later task; what was missing was the visible download action beside it,
 * which section 5 also requires and which the old shell only offered on
 * generated resumes.
 */
export function DocumentFrame({ pdfUrl, downloadUrl, name, testId }: DocumentFrameProps) {
  return (
    <div className="flex h-full min-w-0 flex-col bg-lp-paper-sunken">
      {/*
       * Stacks when narrow. In Split at tablet width this pane can be under
       * 200px wide, and "Download PDF" alone is about 140px of that, so a
       * single row pushes the name to zero width and then overflows anyway.
       */}
      <div
        className={cn(
          "flex shrink-0 flex-col items-start gap-lp-2 border-b border-lp-rule px-lp-4 py-lp-2",
          "lg:h-lp-panel-header lg:flex-row lg:items-center lg:justify-between lg:gap-lp-3 lg:py-0",
        )}
      >
        <p className="max-w-full truncate font-lp-sans text-lp-label font-medium text-lp-ink">
          {name}
        </p>
        {downloadUrl ? (
          <a
            href={downloadUrl}
            download
            data-testid="document-download"
            className={cn(
              "inline-flex h-lp-control shrink-0 items-center gap-lp-2 rounded-lp-control",
              "border border-lp-rule-control bg-lp-paper-raised px-lp-3",
              "font-lp-sans text-lp-label font-medium text-lp-ink",
              "hover:border-lp-rule-strong hover:bg-lp-paper-sunken",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lp-focus",
            )}
          >
            <DownloadSimple size={15} aria-hidden="true" />
            Download PDF
          </a>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 p-lp-4">
        <div className="h-full w-full overflow-hidden rounded-lp-surface shadow-lp-page">
          <PdfPreview pdfUrl={pdfUrl} testId={testId} />
        </div>
      </div>
    </div>
  );
}
