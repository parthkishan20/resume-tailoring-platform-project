"use client";

import * as React from "react";
import { Textarea } from "@/design-system";
import { useWorkspace } from "./WorkspaceContext";

/**
 * The job description. One component, one state, two mount points.
 *
 * This is the whole of D-12. Generate and Evaluate each owned a byte-identical
 * 420px column with its own textarea and its own `useState`, so pasting a
 * description into one left the other empty, and their error styling had
 * already diverged. There is now exactly one field and exactly one string
 * behind it, held by `WorkspaceContext`, which is what DESIGN-SYSTEM.md 3.2
 * means by "paste once, generate, evaluate the result, all without retyping".
 *
 * `id` is passed by the caller so two mounted copies do not both claim the
 * same `for`/`id` pair; the label text differs per tab for the same reason it
 * differs per task.
 */
export function JobDescriptionField({
  id,
  label,
  testId,
  disabled,
  rows = 8,
}: {
  id: string;
  label: string;
  testId?: string;
  disabled?: boolean;
  rows?: number;
}) {
  const { jobDescription, setJobDescription } = useWorkspace();

  return (
    <Textarea
      id={id}
      label={label}
      data-testid={testId}
      value={jobDescription}
      onChange={(event) => setJobDescription(event.target.value)}
      placeholder="Paste the full posting, responsibilities and requirements included."
      helper="Shared by Tailor and Evaluate. Paste it once."
      rows={rows}
      disabled={disabled}
      className="resize-y font-lp-sans"
    />
  );
}
