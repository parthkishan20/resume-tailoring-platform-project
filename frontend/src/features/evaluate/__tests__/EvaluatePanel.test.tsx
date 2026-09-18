import "@/design-system/test-polyfills";
import { TextDecoder, TextEncoder } from "util";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { WorkspaceShell } from "@/features/workspace/WorkspaceShell";
import { renderInWorkspace } from "@/features/test-harness";
import { api } from "@/lib/api";

// jsdom ships neither, and the SSE reader decodes every chunk.
Object.assign(globalThis, { TextDecoder, TextEncoder });

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getMasterResume: jest.fn(),
      saveMasterResume: jest.fn(),
      deleteMasterResume: jest.fn(),
      listResumes: jest.fn(),
      getRules: jest.fn(),
      getResume: jest.fn(),
      getSystemPrompt: jest.fn(),
      getChatHistory: jest.fn(),
      getPdfUrl: (id: number) => `/api/resumes/${id}/pdf`,
    },
  };
});

jest.mock("@/features/document/YamlEditor", () => ({
  YamlEditor: ({ value, onChange }: { value: string; onChange: (next: string) => void }) => (
    <textarea
      data-testid="yaml-editor-input"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));
jest.mock("@/components/PdfPreview", () => ({
  __esModule: true,
  default: () => <div data-testid="pdf-preview-mock" />,
}));
jest.mock("@/components/ResumeListPanel", () => ({
  __esModule: true,
  default: () => <div data-testid="resume-list" />,
}));
jest.mock("@/components/ChatPanel", () => ({
  __esModule: true,
  default: () => <div data-testid="chat-panel" />,
}));

const SAVED_YAML = "cv:\n  name: Saved";
const EDITED_YAML = "cv:\n  name: Edited by hand";

const masterResume = {
  id: 1,
  user_id: "default",
  yaml_content: SAVED_YAML,
  updated_at: "2026-01-01T00:00:00Z",
};

const TAILORED_YAML = "cv:\n  name: Tailored for the role";

const STORED_RESUME = {
  id: 9,
  user_id: "default",
  name: "Resume for a role",
  job_description: "Senior Engineer",
  yaml_content: TAILORED_YAML,
  pdf_path: "9.pdf",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const EVALUATION_RESULT = {
  match_score: 82,
  critique: "Strong alignment with the role's core requirements.",
  matched_keywords: ["Python"],
  missing_keywords: ["Kubernetes"],
};

function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function sseResponse(chunks: string[]): Response {
  let index = 0;
  const reader = {
    read: async () =>
      index < chunks.length
        ? { done: false, value: new TextEncoder().encode(chunks[index++]) }
        : { done: true, value: undefined },
    cancel: async () => undefined,
  };
  return {
    ok: true,
    status: 200,
    body: { getReader: () => reader },
  } as unknown as Response;
}

const fetchMock = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  (api.getMasterResume as jest.Mock).mockResolvedValue(masterResume);
  (api.listResumes as jest.Mock).mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 });
  (api.getRules as jest.Mock).mockResolvedValue([]);
  window.localStorage.clear();
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
});

function lastRequestBody(): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit];
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

async function goToEvaluate() {
  fireEvent.click(await screen.findByTestId("inspector-tab-evaluate"));
  const field = screen.getByLabelText("Job description", { selector: "#evaluate-job-description" });
  fireEvent.change(field, { target: { value: "Senior Engineer" } });
}

describe("D-41: Evaluate operates on the editor's live buffer, not the last save", () => {
  test("evaluating the master sends the unsaved draft directly, with no save first", async () => {
    fetchMock.mockResolvedValue(sseResponse([sseFrame("done", { result: EVALUATION_RESULT })]));

    renderInWorkspace(<WorkspaceShell />);
    const editor = await screen.findByTestId("yaml-editor-input");
    fireEvent.change(editor, { target: { value: EDITED_YAML } });
    await goToEvaluate();

    fireEvent.click(screen.getByTestId("evaluate-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().yaml_content).toBe(EDITED_YAML);
    expect(api.saveMasterResume).not.toHaveBeenCalled();

    expect(await screen.findByTestId("evaluate-result")).toBeInTheDocument();
    expect(screen.getByTestId("score-dial")).toHaveAttribute(
      "aria-label",
      "Match score 82 out of 100. Strong match.",
    );
  });
});

describe("D-45: Evaluate can score the generated resume, not only the master", () => {
  test("after a tailor run, Evaluate scores the tailored document, not the master's YAML", async () => {
    fetchMock.mockImplementation((path: string) => {
      if (path === "/api/resumes/stream") {
        return Promise.resolve(sseResponse([sseFrame("done", { result: STORED_RESUME })]));
      }
      return Promise.resolve(sseResponse([sseFrame("done", { result: EVALUATION_RESULT })]));
    });

    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");
    fireEvent.change(screen.getByTestId("job-description"), {
      target: { value: "Senior Engineer" },
    });
    fireEvent.click(screen.getByTestId("generate-button"));

    // The handoff: generating opens the result and switches to Evaluate.
    await waitFor(() =>
      expect(screen.getByTestId("nav-library")).toHaveAttribute("aria-current", "page"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("inspector-tab-evaluate")).toHaveAttribute("aria-selected", "true"),
    );

    fetchMock.mockClear();
    fireEvent.click(screen.getByTestId("evaluate-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(lastRequestBody().yaml_content).toBe(TAILORED_YAML);
  });

  test("Library open with nothing selected shows a dedicated empty state and disables Evaluate", async () => {
    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");

    fireEvent.click(screen.getByTestId("nav-library"));
    await goToEvaluate();

    expect(screen.getByTestId("evaluate-button")).toBeDisabled();
    expect(screen.getByText("Select a document to evaluate")).toBeInTheDocument();
  });
});
