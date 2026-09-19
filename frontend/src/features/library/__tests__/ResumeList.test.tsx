import "@/design-system/test-polyfills";
import * as React from "react";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import { renderInWorkspace } from "@/features/test-harness";
import { api } from "@/lib/api";
import { ResumeList } from "../ResumeList";

jest.mock("@/lib/api", () => ({
  ApiError: jest.requireActual("@/lib/api").ApiError,
  api: {
    listResumes: jest.fn(),
    updateResume: jest.fn(),
    deleteResume: jest.fn(),
  },
}));

const listResumes = api.listResumes as jest.Mock;
const updateResume = api.updateResume as jest.Mock;
const deleteResume = api.deleteResume as jest.Mock;

const ITEM = {
  id: 1,
  user_id: "default",
  name: "Backend resume",
  job_description: "Senior backend engineer at a fintech startup",
  pdf_path: "/pdfs/1.pdf",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderList(overrides: Partial<React.ComponentProps<typeof ResumeList>> = {}) {
  const onSelect = overrides.onSelect ?? jest.fn();
  const onDeleted = overrides.onDeleted ?? jest.fn();
  return {
    onSelect,
    onDeleted,
    ...renderInWorkspace(
      <ResumeList selected={null} onSelect={onSelect} onDeleted={onDeleted} {...overrides} />,
    ),
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  listResumes.mockResolvedValue({ items: [ITEM], total: 1, page: 1, limit: 20 });
});

// D-76: the row's own onKeyDown (Enter/Space-to-select) must not swallow a
// keydown that actually originated inside one of the row's own controls or a
// dialog they open, since React bubbles synthetic events through the
// component tree rather than the DOM tree.
describe("ResumeListRow keyboard operability (D-76)", () => {
  test("pressing Enter on the rename icon opens the rename dialog, not row-select", async () => {
    const onSelect = jest.fn();
    renderList({ onSelect });
    await screen.findAllByTestId("resume-list-item");

    screen.getByTestId("rename-resume").focus();
    await userEvent.keyboard("{Enter}");

    expect(await screen.findByLabelText("Resume name")).toHaveFocus();
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("pressing Enter on the delete icon opens the delete confirmation, not row-select", async () => {
    const onSelect = jest.fn();
    renderList({ onSelect });
    await screen.findAllByTestId("resume-list-item");

    screen.getByTestId("delete-resume").focus();
    await userEvent.keyboard("{Enter}");

    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("pressing Enter on the rename dialog's Save button actually renames", async () => {
    updateResume.mockResolvedValue({ ...ITEM, name: "Renamed" });
    renderList();
    await screen.findAllByTestId("resume-list-item");

    screen.getByTestId("rename-resume").focus();
    await userEvent.keyboard("{Enter}");
    const input = await screen.findByLabelText("Resume name");
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed");
    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(updateResume).toHaveBeenCalledWith(ITEM.id, { name: "Renamed" }));
  });

  test("pressing Enter on the delete confirmation's Delete action actually deletes", async () => {
    deleteResume.mockResolvedValue(undefined);
    const onDeleted = jest.fn();
    renderList({ onDeleted });
    await screen.findAllByTestId("resume-list-item");

    screen.getByTestId("delete-resume").focus();
    await userEvent.keyboard("{Enter}");
    const confirm = await screen.findByRole("button", { name: "Delete" });
    confirm.focus();
    await userEvent.keyboard("{Enter}");

    await waitFor(() => expect(deleteResume).toHaveBeenCalledWith(ITEM.id));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(ITEM.id));
  });

  test("pressing Enter on the row itself still selects it", async () => {
    const onSelect = jest.fn();
    renderList({ onSelect });
    const [row] = await screen.findAllByTestId("resume-list-item");

    row.focus();
    await userEvent.keyboard("{Enter}");

    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
