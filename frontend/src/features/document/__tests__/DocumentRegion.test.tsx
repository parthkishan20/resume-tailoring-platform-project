import "@/design-system/test-polyfills";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { WorkspaceShell } from "@/features/workspace/WorkspaceShell";
import { renderInWorkspace } from "@/features/test-harness";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  ApiError: jest.requireActual("@/lib/api").ApiError,
  api: {
    getMasterResume: jest.fn(),
    saveMasterResume: jest.fn(),
    deleteMasterResume: jest.fn(),
    listResumes: jest.fn(),
    getRules: jest.fn(),
    getSystemPrompt: jest.fn(),
    getChatHistory: jest.fn(),
    getPdfUrl: (id: number) => `/api/resumes/${id}/pdf`,
  },
}));

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

beforeEach(() => {
  jest.clearAllMocks();
  (api.getMasterResume as jest.Mock).mockResolvedValue(masterResume);
  (api.listResumes as jest.Mock).mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 });
  (api.getRules as jest.Mock).mockResolvedValue([]);
  window.localStorage.clear();
});

async function renderWithEdits() {
  renderInWorkspace(<WorkspaceShell />);
  const editor = await screen.findByTestId("yaml-editor-input");
  fireEvent.change(editor, { target: { value: EDITED_YAML } });
  return editor;
}

describe("D-30: unsaved editor edits survive navigation", () => {
  test("the draft is still there after leaving for the Library and coming back", async () => {
    await renderWithEdits();
    expect(screen.getByText("Unsaved edits")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("nav-library"));
    expect(screen.getByTestId("resume-list")).toBeInTheDocument();
    expect(screen.queryByTestId("yaml-editor-input")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("nav-master"));

    expect(screen.getByTestId("yaml-editor-input")).toHaveValue(EDITED_YAML);
    expect(screen.getByText("Unsaved edits")).toBeInTheDocument();
  });

  test("the draft survives an inspector tab switch and a layout mode change", async () => {
    await renderWithEdits();

    fireEvent.click(screen.getByTestId("inspector-tab-assistant"));
    fireEvent.click(screen.getByTestId("mode-editor"));
    fireEvent.click(screen.getByTestId("mode-split"));

    expect(screen.getByTestId("yaml-editor-input")).toHaveValue(EDITED_YAML);
  });

  test("beforeunload is registered while dirty and removed once saved", async () => {
    const add = jest.spyOn(window, "addEventListener");
    const remove = jest.spyOn(window, "removeEventListener");
    (api.saveMasterResume as jest.Mock).mockResolvedValue({
      ...masterResume,
      yaml_content: EDITED_YAML,
    });

    await renderWithEdits();
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(true);

    fireEvent.click(screen.getByTestId("save-master-resume"));

    await waitFor(() =>
      expect(remove.mock.calls.some(([type]) => type === "beforeunload")).toBe(true),
    );
    add.mockRestore();
    remove.mockRestore();
  });

  test("a clean buffer registers no unload guard, so a reload is not interrupted", async () => {
    const add = jest.spyOn(window, "addEventListener");
    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");

    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(false);
    add.mockRestore();
  });
});

describe("P1-7: server updates do not clobber unsaved edits", () => {
  test("an assistant rewrite arriving mid-edit leaves the draft on screen", async () => {
    const { queryClient } = renderInWorkspace(<WorkspaceShell />);
    const editor = await screen.findByTestId("yaml-editor-input");
    fireEvent.change(editor, { target: { value: EDITED_YAML } });

    // What `AssistantPanel` does when the backend reports the master resume
    // was updated behind the user's back.
    queryClient.setQueryData(["master-resume"], {
      ...masterResume,
      yaml_content: "cv:\n  name: Rewritten by the assistant",
    });

    await waitFor(() => expect(screen.getByTestId("yaml-editor-input")).toHaveValue(EDITED_YAML));
  });

  test("a server update is adopted when there are no local edits", async () => {
    const { queryClient } = renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");

    queryClient.setQueryData(["master-resume"], {
      ...masterResume,
      yaml_content: "cv:\n  name: Rewritten by the assistant",
    });

    await waitFor(() =>
      expect(screen.getByTestId("yaml-editor-input")).toHaveValue(
        "cv:\n  name: Rewritten by the assistant",
      ),
    );
  });
});

describe("the editor and preview split", () => {
  test("the divider only exists in Split, and is keyboard adjustable", async () => {
    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");

    const handle = screen.getByTestId("split-handle");
    expect(handle).toHaveAttribute("aria-valuenow", "50");

    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(screen.getByTestId("split-handle")).toHaveAttribute("aria-valuenow", "52");

    fireEvent.keyDown(screen.getByTestId("split-handle"), { key: "End" });
    expect(screen.getByTestId("split-handle")).toHaveAttribute("aria-valuenow", "75");

    fireEvent.click(screen.getByTestId("mode-editor"));
    expect(screen.queryByTestId("split-handle")).not.toBeInTheDocument();
  });

  test("the split position persists across a remount", async () => {
    const first = renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");
    fireEvent.keyDown(screen.getByTestId("split-handle"), { key: "End" });
    first.unmount();

    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");
    await waitFor(() =>
      expect(screen.getByTestId("split-handle")).toHaveAttribute("aria-valuenow", "75"),
    );
  });
});

describe("saving", () => {
  test("Save is disabled until there is something to save", async () => {
    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("yaml-editor-input");
    expect(screen.getByTestId("save-master-resume")).toBeDisabled();

    fireEvent.change(screen.getByTestId("yaml-editor-input"), { target: { value: EDITED_YAML } });
    expect(screen.getByTestId("save-master-resume")).toBeEnabled();
  });

  test("a failed save reports the reason and keeps the draft", async () => {
    (api.saveMasterResume as jest.Mock).mockRejectedValue(new Error("line 3: mapping expected"));
    await renderWithEdits();

    fireEvent.click(screen.getByTestId("save-master-resume"));

    expect(await screen.findByRole("alert")).toHaveTextContent("line 3: mapping expected");
    expect(screen.getByTestId("yaml-editor-input")).toHaveValue(EDITED_YAML);
  });
});
