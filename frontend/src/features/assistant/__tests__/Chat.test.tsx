import "@/design-system/test-polyfills";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { renderInWorkspace } from "@/features/test-harness";
import { useWorkspace, WorkspaceProvider } from "@/features/workspace/WorkspaceContext";
import { api, streamChat } from "@/lib/api";
import { Chat } from "../Chat";

jest.mock("@/lib/api", () => ({
  ApiError: jest.requireActual("@/lib/api").ApiError,
  api: {
    getChatHistory: jest.fn(),
    getMasterResume: jest.fn(),
    saveMasterResume: jest.fn(),
  },
  streamChat: jest.fn(),
}));

const getChatHistory = api.getChatHistory as jest.Mock;
const getMasterResume = api.getMasterResume as jest.Mock;
const mockStreamChat = streamChat as jest.Mock;

const masterResume = {
  id: 1,
  user_id: "default",
  yaml_content: "cv:\n  name: Test",
  updated_at: "2026-01-01T00:00:00Z",
};

/** An async generator yielding the given SSE frames. */
async function* frames(events: { event: string; data: unknown }[]) {
  for (const frame of events) {
    yield frame;
  }
}

beforeEach(() => {
  jest.clearAllMocks();
  getChatHistory.mockResolvedValue([]);
  getMasterResume.mockResolvedValue(masterResume);
});

/**
 * `Chat` reads `useWorkspace()` (D-86), so every test needs a real
 * `WorkspaceProvider` above it now, not just the query/toast providers
 * `renderInWorkspace` supplies on its own.
 */
function renderChat() {
  return renderInWorkspace(
    <WorkspaceProvider>
      <Chat />
    </WorkspaceProvider>,
  );
}

/** Exposes `setMasterDraft` so a test can open a dirty local draft (D-86). */
function DirtyDraftButton() {
  const { setMasterDraft, masterDirty } = useWorkspace();
  return (
    <button
      type="button"
      data-testid="dirty-draft"
      onClick={() => setMasterDraft("cv:\n  name: Local edit")}
    >
      {masterDirty ? "dirty" : "clean"}
    </button>
  );
}

function renderChatWithDraftControl() {
  return renderInWorkspace(
    <WorkspaceProvider>
      <DirtyDraftButton />
      <Chat />
    </WorkspaceProvider>,
  );
}

describe("loading the transcript", () => {
  test("renders the persisted history, oldest first", async () => {
    getChatHistory.mockResolvedValue([
      {
        id: 1,
        user_id: "default",
        role: "user",
        content: "Hello",
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: 2,
        user_id: "default",
        role: "assistant",
        content: "Hi there",
        created_at: "2026-01-01T00:00:01Z",
      },
    ]);
    renderChat();

    const messages = await screen.findAllByTestId("chat-message");
    expect(messages).toHaveLength(2);
    expect(messages[0]).toHaveTextContent("Hello");
    expect(messages[1]).toHaveTextContent("Hi there");
  });

  test("an empty transcript offers suggested first messages", async () => {
    renderChat();
    expect(await screen.findByText("Ask the assistant for edits")).toBeInTheDocument();
    const suggestions = screen.getAllByTestId("chat-suggestion");
    expect(suggestions.length).toBeGreaterThan(0);

    fireEvent.click(suggestions[0]);
    expect(screen.getByTestId("chat-input")).toHaveValue(suggestions[0].textContent);
  });

  test("a load failure shows a retry action", async () => {
    getChatHistory.mockRejectedValue(new Error("network down"));
    renderChat();

    expect(await screen.findByRole("alert")).toHaveTextContent("network down");

    getChatHistory.mockResolvedValue([]);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(getChatHistory).toHaveBeenCalledTimes(2));
  });
});

describe("chat pagination (D-21)", () => {
  test("only the most recent messages render, with a control to reveal more", async () => {
    const history = Array.from({ length: 45 }, (_, i) => ({
      id: i + 1,
      user_id: "default",
      role: i % 2 === 0 ? "user" : "assistant",
      content: `Message ${i + 1}`,
      created_at: "2026-01-01T00:00:00Z",
    }));
    getChatHistory.mockResolvedValue(history);
    renderChat();

    const messages = await screen.findAllByTestId("chat-message");
    expect(messages).toHaveLength(30);
    expect(screen.getByText("Message 45")).toBeInTheDocument();
    expect(screen.queryByText("Message 1")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("chat-load-earlier"));

    await waitFor(() => expect(screen.getAllByTestId("chat-message")).toHaveLength(45));
    expect(screen.getByText("Message 1")).toBeInTheDocument();
  });
});

describe("sending a message", () => {
  test("streams tokens and lands on the final text", async () => {
    mockStreamChat.mockReturnValue(
      frames([
        { event: "token", data: { delta: "Sure" } },
        { event: "token", data: { delta: ", done." } },
        { event: "done", data: { result: { text: "Sure, done.", action: null } } },
      ]),
    );
    // The `done` frame's cache invalidation refetches the transcript, which a
    // real backend answers with the turn it just persisted.
    getChatHistory.mockResolvedValueOnce([]).mockResolvedValue([
      {
        id: 1,
        user_id: "default",
        role: "user",
        content: "Tighten my summary",
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: 2,
        user_id: "default",
        role: "assistant",
        content: "Sure, done.",
        created_at: "2026-01-01T00:00:01Z",
      },
    ]);
    renderChat();
    await screen.findByTestId("chat-input");

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Tighten my summary" } });
    fireEvent.click(screen.getByTestId("chat-send"));

    expect(mockStreamChat).toHaveBeenCalledWith(
      { message: "Tighten my summary" },
      expect.objectContaining({ signal: expect.anything() }),
    );
    expect(await screen.findByText("Tighten my summary")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Sure, done.")).toBeInTheDocument());
  });

  test("an error frame shows a retryable message", async () => {
    mockStreamChat.mockReturnValue(
      frames([
        { event: "error", data: { error: "The provider is unavailable", code: "LLM_UNAVAILABLE" } },
      ]),
    );
    renderChat();
    await screen.findByTestId("chat-input");

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("chat-send"));

    expect(await screen.findByRole("alert")).toHaveTextContent("The provider is unavailable");
    expect(screen.getByTestId("chat-retry")).toBeInTheDocument();
  });

  test("a tool-call result (D-33 seam) is described without a hardcoded type list", async () => {
    mockStreamChat.mockReturnValue(
      frames([
        {
          event: "done",
          data: {
            result: {
              text: "Done",
              action: { type: "master_resume_updated", resume_id: null },
            },
          },
        },
      ]),
    );
    renderChat();
    await screen.findByTestId("chat-input");

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Update my resume" } });
    fireEvent.click(screen.getByTestId("chat-send"));

    expect(await screen.findByTestId("chat-action-note")).toHaveTextContent(
      "Master resume updated",
    );
  });
});

describe("the assistant/draft race, which is D-86", () => {
  function masterResumeUpdatedFrames() {
    return frames([
      {
        event: "done",
        data: {
          result: {
            text: "Updated your summary.",
            action: { type: "master_resume_updated", resume_id: null },
          },
        },
      },
    ]);
  }

  test("warns when the assistant edits the master resume while a local draft is open and dirty", async () => {
    mockStreamChat.mockReturnValue(masterResumeUpdatedFrames());
    renderChatWithDraftControl();

    const draftButton = await screen.findByTestId("dirty-draft");
    fireEvent.click(draftButton);
    expect(draftButton).toHaveTextContent("dirty");

    fireEvent.change(screen.getByTestId("chat-input"), {
      target: { value: "Tighten my summary" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));

    expect(await screen.findByText("Your open draft is now out of date")).toBeInTheDocument();
    expect(screen.getByText(/saving your draft will overwrite that change/i)).toBeInTheDocument();
  });

  test("does not warn when there is no conflicting local draft open", async () => {
    mockStreamChat.mockReturnValue(masterResumeUpdatedFrames());
    renderChatWithDraftControl();

    const draftButton = await screen.findByTestId("dirty-draft");
    expect(draftButton).toHaveTextContent("clean");

    fireEvent.change(screen.getByTestId("chat-input"), {
      target: { value: "Tighten my summary" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));

    expect(await screen.findByTestId("chat-action-note")).toHaveTextContent(
      "Master resume updated",
    );
    expect(screen.queryByText("Your open draft is now out of date")).not.toBeInTheDocument();
  });

  test("does not warn for an action other than a master-resume edit, even with a dirty draft", async () => {
    mockStreamChat.mockReturnValue(
      frames([
        {
          event: "done",
          data: {
            result: {
              text: "Generated a tailored resume.",
              action: { type: "resume_generated", resume_id: 7 },
            },
          },
        },
      ]),
    );
    renderChatWithDraftControl();

    fireEvent.click(await screen.findByTestId("dirty-draft"));
    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "Tailor this" } });
    fireEvent.click(screen.getByTestId("chat-send"));

    expect(await screen.findByTestId("chat-action-note")).toHaveTextContent("Resume generated");
    expect(screen.queryByText("Your open draft is now out of date")).not.toBeInTheDocument();
  });
});
