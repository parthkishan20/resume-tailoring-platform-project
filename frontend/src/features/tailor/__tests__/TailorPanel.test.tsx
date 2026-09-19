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

const STORED_RESUME = {
  id: 9,
  user_id: "default",
  name: "Resume for a role",
  job_description: "Senior Engineer",
  yaml_content: "cv:\n  name: Tailored",
  pdf_path: "9.pdf",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A `Response` whose body yields the given chunks, once, as an SSE stream. */
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

async function typeJobDescription() {
  const field = await screen.findByTestId("job-description");
  fireEvent.change(field, { target: { value: "Senior Engineer" } });
  return field;
}

describe("B-06: Tailor sends the live buffer directly, without saving first", () => {
  test("an unsaved master edit is sent as yaml_content, with no prior save", async () => {
    fetchMock.mockResolvedValue(sseResponse([sseFrame("done", { result: STORED_RESUME })]));

    renderInWorkspace(<WorkspaceShell />);
    const editor = await screen.findByTestId("yaml-editor-input");
    fireEvent.change(editor, { target: { value: EDITED_YAML } });
    await typeJobDescription();

    fireEvent.click(screen.getByTestId("generate-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    expect(api.saveMasterResume).not.toHaveBeenCalled();
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/resumes/stream");
    expect(JSON.parse(init.body as string)).toMatchObject({ yaml_content: EDITED_YAML });

    // The run actually completes and hands off to Evaluate, proving the SSE
    // frame was read and parsed, not just that the request was sent.
    await waitFor(() =>
      expect(screen.getByTestId("inspector-tab-evaluate")).toHaveAttribute("aria-selected", "true"),
    );
  });

  test("a clean buffer is also sent directly, as the saved YAML", async () => {
    fetchMock.mockResolvedValue(sseResponse([sseFrame("done", { result: STORED_RESUME })]));

    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");
    await typeJobDescription();

    fireEvent.click(screen.getByTestId("generate-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(api.saveMasterResume).not.toHaveBeenCalled();
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body as string)).toMatchObject({ yaml_content: SAVED_YAML });
  });
});
