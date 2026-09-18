"use client";

import * as React from "react";
import { Eraser } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertDialog, AlertDialogContent, AlertDialogTrigger, IconButton } from "@/design-system";
import { queryKeys } from "@/features/queries";
import { api } from "@/lib/api";
import type { MasterResume } from "@/lib/types";
import { Chat } from "./Chat";

/**
 * Assistant (DESIGN-SYSTEM.md 3.2): chat, docked rather than overlaying, so
 * the user can watch the document change while the assistant edits it.
 *
 * `Chat` replaces the re-hosted `components/ChatPanel.tsx` 2.3 kept in place
 * to keep the assistant reachable: real chat pagination (D-21's frontend
 * half), the typed `streamChat` reader instead of a cast `readSseStream`
 * call, and the D-33 tool-call seam all belong here, not in a 20-line
 * pass-through. `components/ChatPanel.tsx` and its test are now unreferenced;
 * PLAN.md's 3.2 entry notes them for a follow-up deletion pass, the same
 * cleanup 3.1 is doing for the panels it supersedes.
 *
 * `masterResume` is accepted, not used: `Chat` invalidates
 * `queryKeys.masterResume` through its own `QueryClient` handle when a tool
 * call reports one, which is the same cache every mounted `useMasterResume`
 * reads from, so no prop needs to carry the refreshed document back up.
 * Kept as a parameter because `Inspector.tsx` (not this task's file) still
 * passes it.
 */
export function AssistantPanel({ masterResume: _masterResume }: { masterResume: MasterResume }) {
  const queryClient = useQueryClient();
  const [chatEpoch, setChatEpoch] = React.useState(0);

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
        <Chat key={chatEpoch} />
      </div>
    </div>
  );
}
