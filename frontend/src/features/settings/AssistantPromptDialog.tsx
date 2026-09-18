"use client";

import * as React from "react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  ErrorState,
  Skeleton,
  Textarea,
  useToast,
} from "@/design-system";
import { useResetSystemPrompt, useSystemPrompt, useUpdateSystemPrompt } from "@/features/queries";

/**
 * The assistant's system prompt (DESIGN-SYSTEM.md 3.2).
 *
 * It had no UI at all before this: the endpoints existed and nothing in the
 * product reached them. It is a settings dialog rather than a destination for
 * the same reason the rules are, which is that editing it is something the
 * user does once and then leaves alone.
 */
export function AssistantPromptDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const prompt = useSystemPrompt(open);
  const update = useUpdateSystemPrompt();
  const reset = useResetSystemPrompt();
  const { toast } = useToast();

  const [draft, setDraft] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open) setDraft(null);
  }, [open]);

  const value = draft ?? prompt.data?.content ?? "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Assistant prompt"
        description="The standing instructions the assistant reads before every message."
      >
        {prompt.isPending ? (
          <Skeleton shape="block" className="h-[180px]" />
        ) : prompt.isError ? (
          <ErrorState
            title="The assistant prompt could not be loaded"
            cause={prompt.error.message}
            action={
              <Button variant="secondary" size="sm" onClick={() => void prompt.refetch()}>
                Try again
              </Button>
            }
          />
        ) : (
          <>
            <Textarea
              id="assistant-prompt"
              label="Instructions"
              data-testid="assistant-prompt"
              value={value}
              onChange={(event) => setDraft(event.target.value)}
              rows={10}
              helper="Applies to every conversation, including the current one."
              error={update.isError ? update.error.message : undefined}
            />
            <DialogFooter>
              <Button
                variant="ghost"
                onClick={() =>
                  reset.mutate(undefined, {
                    onSuccess: () => {
                      setDraft(null);
                      toast({ title: "Assistant prompt reset" });
                    },
                  })
                }
                loading={reset.isPending}
                loadingLabel="Resetting"
              >
                Reset to default
              </Button>
              <Button
                variant="primary"
                data-testid="assistant-prompt-save"
                loading={update.isPending}
                loadingLabel="Saving"
                onClick={() =>
                  update.mutate(value, {
                    onSuccess: () => {
                      setDraft(null);
                      toast({ title: "Assistant prompt saved", tone: "positive" });
                      onOpenChange(false);
                    },
                  })
                }
              >
                Save prompt
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
