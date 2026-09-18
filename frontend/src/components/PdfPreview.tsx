"use client";
import { useState, useEffect } from "react";
import { Skeleton } from "@/design-system";

interface Props {
  pdfUrl: string;
  testId?: string;
}

/**
 * Fetch-to-blob PDF preview. Internals rewritten by task 3.1 onto the
 * Letterpress tokens and the `Skeleton`/`role="alert"` primitives, in place:
 * `components/ResumeListPanel.tsx` (task 3.2's) still imports this by
 * relative path, and `design-system/DocumentFrame.tsx` (promoted by this same
 * task) wraps it, so a design-system primitive depending on the old dark-shell
 * palette (`bg-white`, `text-error`, `border-border`, a bare `ui/Spinner`)
 * would have defeated the point of promoting `DocumentFrame`. Props (`pdfUrl`,
 * `testId`) and behaviour are unchanged, so every existing caller keeps
 * compiling and gets the same visual update for free.
 *
 * Loading renders a page-shaped `Skeleton` rather than a circular spinner
 * (DESIGN-SYSTEM.md 4.2, D-09 in the spec's defect table). The error state is
 * `role="alert"` (section 5, D-44) and shows the server's own message
 * verbatim, matching `ErrorState`'s "cause, when known" convention without
 * reaching for the full primitive, which assumes more horizontal room than
 * this frame reliably has.
 */
export default function PdfPreview({ pdfUrl, testId = "resume-preview" }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let url: string;
    let cancelled = false;
    setBlobUrl(null);
    setError(null);
    fetch(pdfUrl)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail ?? body?.error ?? `Preview failed (${res.status})`);
        }
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Preview failed");
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [pdfUrl]);

  if (error) {
    return (
      <div
        data-testid={testId}
        role="alert"
        className="flex h-full items-center justify-center p-lp-5"
      >
        <p className="max-w-sm select-text text-center font-lp-sans text-lp-body text-lp-critical">
          {error}
        </p>
      </div>
    );
  }

  if (!blobUrl) {
    return (
      <div
        data-testid={testId}
        aria-busy="true"
        className="flex h-full flex-col items-center justify-center gap-lp-3 p-lp-5"
      >
        <p aria-live="polite" className="sr-only">
          Rendering the PDF
        </p>
        <Skeleton shape="page" />
      </div>
    );
  }

  return (
    <div className="h-full w-full p-lp-3">
      <iframe
        data-testid={testId}
        src={`${blobUrl}#toolbar=0&navpanes=0`}
        className="h-full w-full rounded-lp-control border border-lp-rule bg-white"
        title="Resume PDF Preview"
      />
    </div>
  );
}
