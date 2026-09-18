import "@/design-system/test-polyfills";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { WorkspaceShell } from "../WorkspaceShell";
import { renderInWorkspace } from "@/features/test-harness";
import { api, ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return {
    ApiError: actual.ApiError,
    api: {
      getMasterResume: jest.fn(),
      saveMasterResume: jest.fn(),
      deleteMasterResume: jest.fn(),
      listResumes: jest.fn(),
      getRules: jest.fn(),
      updateRules: jest.fn(),
      resetRules: jest.fn(),
      getSystemPrompt: jest.fn(),
      updateSystemPrompt: jest.fn(),
      resetSystemPrompt: jest.fn(),
      getChatHistory: jest.fn(),
      clearChat: jest.fn(),
      getPdfUrl: (id: number) => `/api/resumes/${id}/pdf`,
    },
  };
});

// The document region pulls in CodeMirror and the PDF pipeline; neither is
// under test here and neither works in jsdom.
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

const masterResume = {
  id: 1,
  user_id: "default",
  yaml_content: "cv:\n  name: Test",
  updated_at: "2026-01-01T00:00:00Z",
};

const getMasterResume = api.getMasterResume as jest.Mock;
const listResumes = api.listResumes as jest.Mock;
const getRules = api.getRules as jest.Mock;
const getSystemPrompt = api.getSystemPrompt as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  getMasterResume.mockResolvedValue(masterResume);
  listResumes.mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 });
  getRules.mockResolvedValue([{ section: "experience", rule_key: "max_bullets", rule_value: "4" }]);
  getSystemPrompt.mockResolvedValue({
    id: 1,
    user_id: "default",
    content: "You are a careful resume editor.",
    updated_at: "2026-01-01T00:00:00Z",
  });
  window.localStorage.clear();
});

describe("routing between the three shell states", () => {
  test("renders the workspace once the master resume loads", async () => {
    renderInWorkspace(<WorkspaceShell />);
    expect(await screen.findByTestId("nav-rail")).toBeInTheDocument();
    expect(screen.getByTestId("inspector")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Master resume" })).toBeInTheDocument();
  });

  test("renders onboarding when there is genuinely no master resume", async () => {
    getMasterResume.mockResolvedValue(null);
    renderInWorkspace(<WorkspaceShell />);
    expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
  });

  test("renders an error screen, not onboarding, when the load fails", async () => {
    getMasterResume.mockRejectedValue(new ApiError("database is locked", 500, "DB_ERROR"));
    renderInWorkspace(<WorkspaceShell />);

    expect(await screen.findByTestId("load-error")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("database is locked");
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-rail")).not.toBeInTheDocument();
  });

  test("the retry action reloads and recovers", async () => {
    getMasterResume
      .mockRejectedValueOnce(new ApiError("Service Unavailable", 503, "LLM_UNAVAILABLE"))
      .mockResolvedValueOnce(masterResume);
    renderInWorkspace(<WorkspaceShell />);

    fireEvent.click(await screen.findByTestId("load-error-retry"));

    await waitFor(() => expect(getMasterResume).toHaveBeenCalledTimes(2));
    expect(await screen.findByTestId("nav-rail")).toBeInTheDocument();
    expect(screen.queryByTestId("load-error")).not.toBeInTheDocument();
  });
});

describe("information architecture", () => {
  test("the nav offers two destinations and three settings entries, and no Generate or Chat", async () => {
    renderInWorkspace(<WorkspaceShell />);
    const nav = await screen.findByTestId("nav-rail");

    expect(within(nav).getByTestId("nav-master")).toBeInTheDocument();
    expect(within(nav).getByTestId("nav-library")).toBeInTheDocument();
    expect(within(nav).getByTestId("nav-rules")).toBeInTheDocument();
    expect(within(nav).getByTestId("nav-prompt")).toBeInTheDocument();
    expect(within(nav).getByTestId("nav-appearance")).toBeInTheDocument();

    // The four-destination rail and its bolted-on chat toggle are gone.
    expect(within(nav).queryByTestId("nav-generate")).not.toBeInTheDocument();
    expect(within(nav).queryByTestId("nav-evaluate")).not.toBeInTheDocument();
    expect(within(nav).queryByTestId("nav-chat")).not.toBeInTheDocument();
  });

  test("Master is the current destination and Library replaces the centre", async () => {
    renderInWorkspace(<WorkspaceShell />);
    const master = await screen.findByTestId("nav-master");
    expect(master).toHaveAttribute("aria-current", "page");

    fireEvent.click(screen.getByTestId("nav-library"));

    expect(screen.getByTestId("nav-library")).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("resume-list")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Master resume" })).not.toBeInTheDocument();
  });

  test("the inspector has exactly three tabs and keeps them all mounted", async () => {
    renderInWorkspace(<WorkspaceShell />);
    const inspector = await screen.findByTestId("inspector");

    expect(within(inspector).getAllByRole("tab")).toHaveLength(3);
    // forceMount: the assistant is in the DOM even while Tailor is selected,
    // so switching tabs cannot refetch the conversation.
    expect(within(inspector).getByTestId("chat-panel")).toBeInTheDocument();
  });

  test("the library count in the nav comes from the total, not the row count", async () => {
    listResumes.mockResolvedValue({ items: [], total: 42, page: 1, limit: 20 });
    renderInWorkspace(<WorkspaceShell />);
    const library = await screen.findByTestId("nav-library");
    await waitFor(() => expect(library).toHaveTextContent("42"));
  });
});

describe("the shared job description, which is D-12", () => {
  test("text typed under Tailor is already there under Evaluate", async () => {
    renderInWorkspace(<WorkspaceShell />);

    const tailorField = await screen.findByTestId("job-description");
    fireEvent.change(tailorField, { target: { value: "Senior Platform Engineer" } });

    fireEvent.click(screen.getByTestId("inspector-tab-evaluate"));

    const evaluateField = screen.getByLabelText("Job description", {
      selector: "#evaluate-job-description",
    });
    expect(evaluateField).toHaveValue("Senior Platform Engineer");
  });

  test("there is exactly one job-description state behind the two fields", async () => {
    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("job-description");

    const evaluateField = screen.getByLabelText("Job description", {
      selector: "#evaluate-job-description",
    });
    fireEvent.change(evaluateField, { target: { value: "Staff Engineer" } });

    expect(screen.getByTestId("job-description")).toHaveValue("Staff Engineer");
  });

  test("both run actions stay disabled until a job description exists", async () => {
    renderInWorkspace(<WorkspaceShell />);

    expect(await screen.findByTestId("generate-button")).toBeDisabled();
    expect(screen.getByTestId("evaluate-button")).toBeDisabled();

    fireEvent.change(screen.getByTestId("job-description"), {
      target: { value: "Backend Engineer" },
    });

    expect(screen.getByTestId("generate-button")).toBeEnabled();
    expect(screen.getByTestId("evaluate-button")).toBeEnabled();
  });
});

describe("settings open as dialogs rather than replacing the workspace", () => {
  test("Appearance opens a dialog and the workspace stays mounted behind it", async () => {
    renderInWorkspace(<WorkspaceShell />);
    fireEvent.click(await screen.findByTestId("nav-appearance"));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("theme-light")).toBeInTheDocument();
    expect(screen.getByTestId("nav-rail")).toBeInTheDocument();
  });

  test("a settings query does not run until its dialog is opened", async () => {
    renderInWorkspace(<WorkspaceShell />);
    await screen.findByTestId("nav-prompt");

    // The dialog is mounted from first paint so it can animate, but a query in
    // a component body fires on mount whether or not anything shows its
    // result, so it is gated on `open`.
    expect(getSystemPrompt).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("nav-prompt"));

    await waitFor(() => expect(getSystemPrompt).toHaveBeenCalledTimes(1));
  });

  test("Generation rules opens a labelled form, closing P2-31", async () => {
    renderInWorkspace(<WorkspaceShell />);
    fireEvent.click(await screen.findByTestId("nav-rules"));

    const form = await screen.findByTestId("rules-form");
    expect(within(form).getByLabelText("experience, max bullets")).toBeInTheDocument();
  });
});

describe("the inspector is collapsible and resizable", () => {
  test("collapsing leaves a strip that brings it back", async () => {
    renderInWorkspace(<WorkspaceShell />);
    fireEvent.click(await screen.findByTestId("inspector-collapse"));

    expect(screen.queryByTestId("inspector")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("inspector-expand"));
    expect(screen.getByTestId("inspector")).toBeInTheDocument();
  });

  test("the divider is a keyboard-operable separator within the specified range", async () => {
    renderInWorkspace(<WorkspaceShell />);
    const handle = await screen.findByTestId("inspector-handle");

    expect(handle).toHaveAttribute("role", "separator");
    expect(handle).toHaveAttribute("aria-valuemin", "320");
    expect(handle).toHaveAttribute("aria-valuemax", "560");
    expect(handle).toHaveAttribute("aria-valuenow", "380");

    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(handle).toHaveAttribute("aria-valuenow", "364");

    fireEvent.keyDown(handle, { key: "Home" });
    expect(handle).toHaveAttribute("aria-valuenow", "320");

    // Clamped, not wrapped.
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(handle).toHaveAttribute("aria-valuenow", "320");
  });
});
