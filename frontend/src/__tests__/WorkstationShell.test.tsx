import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import WorkstationShell from "@/components/WorkstationShell";
import { api, ApiError } from "@/lib/api";

jest.mock("@/lib/api", () => {
  const actual = jest.requireActual("@/lib/api");
  return { ApiError: actual.ApiError, api: { getMasterResume: jest.fn(), saveMasterResume: jest.fn() } };
});

// The shell's children pull in CodeMirror, SSE, and PdfPreview; none are under test here.
jest.mock("@/components/Sidebar", () => ({ __esModule: true, default: () => <div /> }));
jest.mock("@/components/MasterResumePanel", () => ({
  __esModule: true,
  default: () => <div data-testid="master-resume-panel" />,
}));
jest.mock("@/components/GenerationPanel", () => ({ __esModule: true, default: () => <div /> }));
jest.mock("@/components/ResumeListPanel", () => ({ __esModule: true, default: () => <div /> }));
jest.mock("@/components/EvaluationPanel", () => ({ __esModule: true, default: () => <div /> }));
jest.mock("@/components/ChatDrawer", () => ({ __esModule: true, default: () => <div /> }));

const mockResume = {
  id: 1, user_id: "default", yaml_content: "cv:\n  name: Test", updated_at: "2026-01-01",
};

const getMasterResume = api.getMasterResume as jest.Mock;

beforeEach(() => {
  getMasterResume.mockReset();
});

test("renders the workstation once the master resume loads", async () => {
  getMasterResume.mockResolvedValue(mockResume);
  render(<WorkstationShell />);
  expect(await screen.findByTestId("master-resume-panel")).toBeInTheDocument();
});

test("renders onboarding when there is genuinely no master resume", async () => {
  getMasterResume.mockResolvedValue(null);
  render(<WorkstationShell />);
  expect(await screen.findByTestId("empty-state")).toBeInTheDocument();
});

test("renders an error screen, not onboarding, when the load fails", async () => {
  getMasterResume.mockRejectedValue(new ApiError("database is locked", 500, "DB_ERROR"));
  render(<WorkstationShell />);

  expect(await screen.findByTestId("load-error")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("database is locked");
  expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  expect(screen.queryByTestId("master-resume-panel")).not.toBeInTheDocument();
});

test("the retry action reloads and recovers", async () => {
  getMasterResume
    .mockRejectedValueOnce(new ApiError("Service Unavailable", 503, "LLM_UNAVAILABLE"))
    .mockResolvedValueOnce(mockResume);
  render(<WorkstationShell />);

  fireEvent.click(await screen.findByTestId("load-error-retry"));

  await waitFor(() => expect(getMasterResume).toHaveBeenCalledTimes(2));
  expect(await screen.findByTestId("master-resume-panel")).toBeInTheDocument();
  expect(screen.queryByTestId("load-error")).not.toBeInTheDocument();
});
