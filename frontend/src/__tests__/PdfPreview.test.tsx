import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import PdfPreview from "@/components/PdfPreview";

const ORIGINAL_CREATE_OBJECT_URL = URL.createObjectURL;
const ORIGINAL_REVOKE_OBJECT_URL = URL.revokeObjectURL;

beforeEach(() => {
  URL.createObjectURL = jest.fn(() => "blob:mock");
  URL.revokeObjectURL = jest.fn();
});

afterEach(() => {
  URL.createObjectURL = ORIGINAL_CREATE_OBJECT_URL;
  URL.revokeObjectURL = ORIGINAL_REVOKE_OBJECT_URL;
  jest.restoreAllMocks();
});

describe("PdfPreview", () => {
  test("shows a page-shaped, non-circular loading state while the fetch is in flight", () => {
    global.fetch = jest.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    render(<PdfPreview pdfUrl="/api/master-resume/preview" />);

    const region = screen.getByTestId("resume-preview");
    expect(region).toHaveAttribute("aria-busy", "true");
  });

  test("renders the PDF in an iframe once the blob resolves", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob(["%PDF"], { type: "application/pdf" })),
    }) as unknown as typeof fetch;

    render(<PdfPreview pdfUrl="/api/master-resume/preview" testId="generated-resume-preview" />);

    await waitFor(() =>
      expect(screen.getByTestId("generated-resume-preview").tagName).toBe("IFRAME"),
    );
    expect(screen.getByTestId("generated-resume-preview")).toHaveAttribute(
      "title",
      "Resume PDF Preview",
    );
  });

  test("a failed render surfaces the server's own message as an alert", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: () => Promise.resolve({ detail: "This resume is not valid: cv.name: field required" }),
    }) as unknown as typeof fetch;

    render(<PdfPreview pdfUrl="/api/master-resume/preview" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This resume is not valid: cv.name: field required",
    );
  });
});
