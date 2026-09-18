"use client";

import * as React from "react";
import { Eraser } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import ChatPanel from "@/components/ChatPanel";
import { AlertDialog, AlertDialogContent, AlertDialogTrigger, IconButton } from "@/design-system";
import { queryKeys } from "@/features/queries";
import { api } from "@/lib/api";
import type { MasterResume } from "@/lib/types";

/**
 * Assistant (DESIGN-SYSTEM.md 3.2): chat, docked rather than overlaying, so
 * the user can watch the document change while the assistant edits it.
 *
 * `ChatPanel` is re-hosted verbatim. It was already a 380px vertical column,
 * which is exactly the inspector's shape, so nothing about it needed to move;
 * what is gone is `ChatDrawer`, the 48-line wrapper that made chat look like a
 * fourth destination and overlaid the work it was editing (defect 8 in the
 * spec's section 1 table, P1-20 in the audit).
 *
 * Its two pieces of surrounding behaviour come with it and are improved in
 * passing: the clear action is now a real `AlertDialog` rather than a bare
 * icon that wipes the conversation on one click, and "master resume updated"
 * writes through the query cache instead of a prop callback that the old shell
 * had to thread two levels down.
 */
export function AssistantPanel({ masterResume }: { masterResume: MasterResume }) {
  const queryClient = useQueryClient();
  const [chatEpoch, setChatEpoch] = React.useState(0);

  const handleAction = React.useCallback(
    (updated: MasterResume) => {
      queryClient.setQueryData(queryKeys.masterResume, updated);
    },
    [queryClient],
  );

  async function clearConversation() {
    try {
      await api.clearChat();
    } catch {
      // The remount below refetches either way, so a failed clear shows the
      // conversation that is genuinely still there rather than a false empty.
    }
    queryClient.removeQueries({ queryKey: queryKeys.chatHistory });
    setChatEpoch((epoch) => epoch + 1);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-lp-panel-header shrink-0 items-center justify-between gap-lp-2 border-b border-lp-rule px-lp-4">
        <h2 className="font-lp-sans text-lp-heading font-semibold text-lp-ink">Assistant</h2>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <IconButton
              label="Clear conversation"
              icon={<Eraser size={16} />}
              size="sm"
              data-testid="chat-clear"
            />
          </AlertDialogTrigger>
          <AlertDialogContent
            title="Clear the conversation?"
            description="The message history is deleted. Any edits the assistant already made to your resume are kept."
            confirmLabel="Clear"
            onConfirm={() => void clearConversation()}
          />
        </AlertDialog>
      </div>
      <div className="min-h-0 flex-1">
        <ChatPanel key={chatEpoch} masterResume={masterResume} onAction={handleAction} />
      </div>
    </div>
  );
}
