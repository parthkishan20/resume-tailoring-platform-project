import "@/design-system/test-polyfills";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { renderInWorkspace } from "@/features/test-harness";
import { WorkspaceProvider } from "@/features/workspace/WorkspaceContext";
import { api } from "@/lib/api";
import { LibraryDocument } from "../LibraryDocument";

jest.mock("@/lib/api", () => ({
  ApiError: jest.requireActual("@/lib/api").ApiError,
  api: {
    listResumes: jest.fn(),
    getResume: jest.fn(),
    updateResume: jest.fn(),
    renderResume: jest.fn(),
    deleteResume: jest.fn(),
    getPdfUrl: (id: number) => `/api/resumes/${id}/pdf`,
  },
}));

jest.mock("@/features/document/YamlEditor", () => ({
  YamlEditor: ({ value, onChange }: { value: string; onChange: (next: string) => void }) => (
    <textarea
      data-testid="resume-yaml-editor-input"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));
jest.mock("@/components/PdfPreview", () => ({
  __esModule: true,
  default: () => <div data-testid="pdf-preview-mock" />,
}));

const listResumes = api.listResumes as jest.Mock;
const getResume = api.getResume as jest.Mock;
const updateResume = api.updateResume as jest.Mock;
const renderResume = api.renderResume as jest.Mock;
const deleteResume = api.deleteResume as jest.Mock;

const ITEM_A = {
  id: 1,
  user_id: "default",
  name: "Backend resume",
  job_description: "Senior backend engineer at a fintech startup",
  pdf_path: "/pdfs/1.pdf",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const ITEM_B = {
  id: 2,
  user_id: "default",
  name: "Platform resume",
  job_description: "Platform engineer",
  pdf_path: null,
  created_at: "2026-01-02T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

function renderLibrary() {
  return renderInWorkspace(
    <WorkspaceProvider>
      <LibraryDocument />
    </WorkspaceProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  listResumes.mockResolvedValue({ items: [ITEM_A, ITEM_B], total: 2, page: 1, limit: 20 });
  getResume.mockResolvedValue({ ...ITEM_A, yaml_content: "cv:\n  name: Backend" });
});

describe("the list", () => {
  test("renders every row with a name and a job description", async () => {
    renderLibrary();
    const rows = await screen.findAllByTestId("resume-list-item");
    expect(rows).toHaveLength(2);
    expect(screen.getByText("Backend resume")).toBeInTheDocument();
    expect(screen.getByText("Platform resume")).toBeInTheDocument();
  });

  test("shows the empty state and no pagination when the library is empty", async () => {
    listResumes.mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 });
    renderLibrary();
    expect(await screen.findByText("No tailored resumes yet")).toBeInTheDocument();
    expect(screen.queryByTestId("library-page-next")).not.toBeInTheDocument();
  });

  test("sorting by job description asks the API for that sort (D-45)", async () => {
    renderLibrary();
    await screen.findAllByTestId("resume-list-item");

    fireEvent.click(screen.getByTestId("sort-jd"));

    await waitFor(() =>
      expect(listResumes).toHaveBeenLastCalledWith("jd", "desc", 1, expect.anything()),
    );
  });

  test("the order toggle flips ascending and descending", async () => {
    renderLibrary();
    await screen.findAllByTestId("resume-list-item");

    fireEvent.click(screen.getByTestId("sort-order-toggle"));

    await waitFor(() =>
      expect(listResumes).toHaveBeenLastCalledWith("date", "asc", 1, expect.anything()),
    );
  });

  test("pagination pages through the library (D-45)", async () => {
    listResumes.mockResolvedValue({ items: [ITEM_A, ITEM_B], total: 45, page: 1, limit: 20 });
    renderLibrary();
    await screen.findAllByTestId("resume-list-item");

    expect(screen.getByTestId("library-page-status")).toHaveTextContent("Page 1 of 3");
    expect(screen.getByTestId("library-page-prev")).toBeDisabled();

    fireEvent.click(screen.getByTestId("library-page-next"));

    await waitFor(() =>
      expect(listResumes).toHaveBeenLastCalledWith("date", "desc", 2, expect.anything()),
    );
  });

  test("deleting a resume calls the API and refreshes the list", async () => {
    deleteResume.mockResolvedValue(undefined);
    renderLibrary();
    const rows = await screen.findAllByTestId("resume-list-item");

    fireEvent.click(within(rows[0]).getByTestId("delete-resume"));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));

    await waitFor(() => expect(deleteResume).toHaveBeenCalledWith(ITEM_A.id));
  });

  test("renaming a resume from the list calls the API with the new name (D-45)", async () => {
    updateResume.mockResolvedValue({ ...ITEM_A, name: "Renamed" });
    renderLibrary();
    const rows = await screen.findAllByTestId("resume-list-item");

    fireEvent.click(within(rows[0]).getByTestId("rename-resume"));
    const input = await screen.findByLabelText("Resume name");
    fireEvent.change(input, { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(updateResume).toHaveBeenCalledWith(ITEM_A.id, { name: "Renamed" }));
  });
});

describe("opening a document", () => {
  test("selecting a row loads and shows the resume's YAML editor", async () => {
    renderLibrary();
    const rows = await screen.findAllByTestId("resume-list-item");

    fireEvent.click(rows[0]);

    await waitFor(() => expect(getResume).toHaveBeenCalledWith(ITEM_A.id, expect.anything()));
    expect(await screen.findByTestId("resume-yaml-editor-input")).toHaveValue(
      "cv:\n  name: Backend",
    );
    expect(screen.getByRole("heading", { name: "Backend resume" })).toBeInTheDocument();
  });

  test("editing the YAML enables Save, and saving calls updateResume (D-45)", async () => {
    updateResume.mockResolvedValue({ ...ITEM_A, yaml_content: "cv:\n  name: Edited" });
    renderLibrary();
    const rows = await screen.findAllByTestId("resume-list-item");
    fireEvent.click(rows[0]);

    const editor = await screen.findByTestId("resume-yaml-editor-input");
    expect(screen.getByTestId("save-resume")).toBeDisabled();

    fireEvent.change(editor, { target: { value: "cv:\n  name: Edited" } });
    expect(screen.getByTestId("save-resume")).toBeEnabled();

    fireEvent.click(screen.getByTestId("save-resume"));

    await waitFor(() =>
      expect(updateResume).toHaveBeenCalledWith(ITEM_A.id, { yaml_content: "cv:\n  name: Edited" }),
    );
  });

  test("Re-render calls the render endpoint (D-45)", async () => {
    renderResume.mockResolvedValue({ ...ITEM_A });
    renderLibrary();
    const rows = await screen.findAllByTestId("resume-list-item");
    fireEvent.click(rows[0]);

    await screen.findByTestId("resume-yaml-editor-input");
    fireEvent.click(screen.getByTestId("render-resume"));

    await waitFor(() => expect(renderResume).toHaveBeenCalledWith(ITEM_A.id));
  });

  test("nothing selected shows the empty prompt instead of a document", async () => {
    renderLibrary();
    await screen.findAllByTestId("resume-list-item");
    expect(screen.getByText("Select a resume")).toBeInTheDocument();
  });
});
