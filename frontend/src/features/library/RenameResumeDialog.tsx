"use client";

import * as React from "react";
import { PencilSimple } from "@phosphor-icons/react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTrigger,
  IconButton,
  Input,
} from "@/design-system";

/** Rename affordance for one resume (D-45). Shared by the list row and the document header. */
export function RenameResumeDialog({
  name,
  onRename,
  pending,
  testId,
}: {
  name: string;
  onRename: (name: string) => void;
  pending: boolean;
  testId: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState(name);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setDraft(name);
      }}
    >
      <DialogTrigger asChild>
        <IconButton
          label="Rename resume"
          icon={<PencilSimple size={14} />}
          size="sm"
          data-testid={testId}
          onClick={(event) => event.stopPropagation()}
        />
      </DialogTrigger>
      <DialogContent title="Rename resume">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const trimmed = draft.trim();
            if (trimmed.length === 0 || trimmed === name) {
              setOpen(false);
              return;
            }
            onRename(trimmed);
            setOpen(false);
          }}
        >
          <Input
            label="Resume name"
            data-testid="rename-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            autoFocus
            maxLength={200}
          />
          <DialogFooter>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              loading={pending}
              loadingLabel="Renaming"
            >
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
