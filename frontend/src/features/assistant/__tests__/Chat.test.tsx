import "@/design-system/test-polyfills";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { renderInWorkspace } from "@/features/test-harness";
import { api, streamChat } from "@/lib/api";
import { Chat } from "../Chat";

jest.mock("@/lib/api", () => ({
  ApiError: jest.requireActual("@/lib/api").ApiError,
  api: {
    getChatHistory: jest.fn(),
  },
  streamChat: jest.fn(),
}));

const getChatHistory = api.getChatHistory as jest.Mock;
const mockStreamChat = streamChat as jest.Mock;

/** An async generator yielding the given SSE frames. */
async function* frames(events: { event: string; data: unknown }[]) {
  for (const frame of events) {
    yield frame;
  }
}

beforeEach(() => {
  jest.clearAllMocks();
  getChatHistory.mockResolvedValue([]);
});

function renderChat() {
  return renderInWorkspace(<Chat />);
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

describe("chat pagination (B-07, D-21)", () => {
  test("only the most recent page renders, with a control that fetches an older page over the wire", async () => {
    const history = Array.from({ length: 45 }, (_, i) => ({
      id: i + 1,
      user_id: "default",
      role: i % 2 === 0 ? "user" : "assistant",
      content: `Message ${i + 1}`,
      created_at: "2026-01-01T00:00:00Z",
    }));

    // A real cursor-paginated backend: each call returns only the `limit`
    // messages immediately before `beforeId` (or the most recent `limit` when
    // `beforeId` is absent), so this fails unless the client actually narrows
    // the request instead of windowing an already-fully-fetched array.
    getChatHistory.mockImplementation(
      async (params?: { limit?: number; beforeId?: number }) => {
        const ceiling = params?.beforeId ?? history.length + 1;
        const older = history.filter((m) => m.id < ceiling);
        return params?.limit ? older.slice(-params.limit) : older;
      },
    );

    renderChat();

    const messages = await screen.findAllByTestId("chat-message");
    expect(messages).toHaveLength(30);
    expect(screen.getByText("Message 45")).toBeInTheDocument();
    expect(screen.queryByText("Message 1")).not.toBeInTheDocument();
    expect(getChatHistory).toHaveBeenCalledWith(
      { limit: 30, beforeId: undefined },
      expect.objectContaining({ signal: expect.anything() }),
    );

    fireEvent.click(screen.getByTestId("chat-load-earlier"));

    await waitFor(() => expect(screen.getAllByTestId("chat-message")).toHaveLength(45));
    expect(screen.getByText("Message 1")).toBeInTheDocument();

    // The second page was requested with the oldest id already held as the
    // cursor, not merely revealed from data already fetched.
    expect(getChatHistory).toHaveBeenCalledWith(
      { limit: 30, beforeId: 16 },
      expect.objectContaining({ signal: expect.anything() }),
    );

    // Fewer than a full page came back, so there is nothing left to load.
    expect(screen.queryByTestId("chat-load-earlier")).not.toBeInTheDocument();
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
