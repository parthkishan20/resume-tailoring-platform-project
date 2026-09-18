import "@/design-system/test-polyfills";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom";
import { OnboardingRoute } from "../OnboardingRoute";
import { renderInWorkspace } from "@/features/test-harness";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  ApiError: jest.requireActual("@/lib/api").ApiError,
  api: { importPdf: jest.fn(), saveMasterResume: jest.fn() },
}));

const imported = {
  id: 1,
  user_id: "default",
  yaml_content: "cv:\n  name: Imported",
  updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  jest.clearAllMocks();
  (api.importPdf as jest.Mock).mockResolvedValue(imported);
  (api.saveMasterResume as jest.Mock).mockResolvedValue(imported);
});

describe("D-39: keyboard users can import a PDF", () => {
  test("the file input is in the tab order, not removed from it", async () => {
    renderInWorkspace(<OnboardingRoute />);

    const input = screen.getByLabelText(/Import a resume PDF/);
    expect(input).toHaveAttribute("type", "file");

    // The defect was `className="hidden"`, which is `display: none` and takes
    // the control out of the tab order entirely. `sr-only` keeps it in.
    expect(input).not.toHaveClass("hidden");
    expect(input).toHaveClass("sr-only");
    expect(input).not.toHaveAttribute("tabindex", "-1");
    expect(input).toBeEnabled();

    await userEvent.tab();
    await waitFor(() => expect(input).toHaveFocus());
  });

  test("the zone is labelled by a real label bound to the input", () => {
    renderInWorkspace(<OnboardingRoute />);
    const input = screen.getByLabelText(/Import a resume PDF/);
    const label = document.querySelector('label[for="pdf-import-input"]');

    expect(input).toHaveAttribute("id", "pdf-import-input");
    expect(label).not.toBeNull();
  });

  test("choosing a file imports it", async () => {
    renderInWorkspace(<OnboardingRoute />);
    const input = screen.getByLabelText(/Import a resume PDF/);
    const file = new File(["%PDF-1.4"], "resume.pdf", { type: "application/pdf" });

    await userEvent.upload(input, file);

    await waitFor(() => expect(api.importPdf).toHaveBeenCalledWith(file));
  });

  test("a non-PDF is refused with a reason rather than silently", async () => {
    renderInWorkspace(<OnboardingRoute />);
    const zone = screen.getByTestId("pdf-import-zone");
    const file = new File(["not a pdf"], "resume.docx", { type: "application/msword" });

    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    expect(await screen.findByRole("alert")).toHaveTextContent("That is not a PDF");
    expect(api.importPdf).not.toHaveBeenCalled();
  });

  test("a failed import reports the backend's own message", async () => {
    (api.importPdf as jest.Mock).mockRejectedValue(new Error("The PDF has no extractable text"));
    renderInWorkspace(<OnboardingRoute />);

    await userEvent.upload(
      screen.getByLabelText(/Import a resume PDF/),
      new File(["%PDF-1.4"], "resume.pdf", { type: "application/pdf" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("The PDF has no extractable text");
  });
});

describe("the three ranked entry paths", () => {
  test("all three are present and keyboard reachable", () => {
    renderInWorkspace(<OnboardingRoute />);

    expect(screen.getByLabelText(/Import a resume PDF/)).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-sample")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-scratch")).toBeInTheDocument();
    expect(screen.getByTestId("onboarding-download")).toHaveAttribute(
      "download",
      "master-resume.yaml",
    );
  });

  test("the sample path persists immediately, so the workspace is usable at once", async () => {
    renderInWorkspace(<OnboardingRoute />);
    fireEvent.click(screen.getByTestId("onboarding-sample"));

    await waitFor(() => expect(api.saveMasterResume).toHaveBeenCalledTimes(1));
    const yaml = (api.saveMasterResume as jest.Mock).mock.calls[0][0] as string;
    expect(yaml).toContain("cv:");
    expect(yaml).toContain("experience:");
  });

  test("writing from scratch seeds the least that renders", async () => {
    renderInWorkspace(<OnboardingRoute />);
    fireEvent.click(screen.getByTestId("onboarding-scratch"));

    await waitFor(() => expect(api.saveMasterResume).toHaveBeenCalledTimes(1));
    const yaml = (api.saveMasterResume as jest.Mock).mock.calls[0][0] as string;
    expect(yaml).toContain("cv:");
    expect(yaml).not.toContain("Your University");
  });
});

describe("copy constraints from DESIGN-SYSTEM.md 3.3 and section 7", () => {
  test("no em dash appears anywhere on the first-run surface", () => {
    const { container } = renderInWorkspace(<OnboardingRoute />);
    expect(container.textContent ?? "").not.toContain("—");
  });

  test("there is one headline and at most one eyebrow", () => {
    renderInWorkspace(<OnboardingRoute />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
  });
});
