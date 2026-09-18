import "../test-polyfills";
import * as React from "react";
import { render, screen } from "@testing-library/react";
import { Chip } from "../Chip";
import { EmptyState } from "../EmptyState";
import { ErrorState } from "../ErrorState";
import { ProgressRail } from "../ProgressRail";
import { Skeleton } from "../Skeleton";

const STAGES = [
  { id: "read", label: "Reading the job description" },
  { id: "tailor", label: "Tailoring the resume" },
  { id: "render", label: "Rendering the PDF" },
];

describe("Chip", () => {
  it("carries its meaning in text, not only in colour", () => {
    render(
      <Chip tone="critical" toneLabel="Missing">
        terraform
      </Chip>,
    );
    expect(screen.getByText("Missing:")).toBeInTheDocument();
    expect(screen.getByText("terraform")).toBeInTheDocument();
  });

  it("uses the pill radius, which 2.3 allows on chips", () => {
    const { container } = render(<Chip>python</Chip>);
    expect(container.firstElementChild).toHaveClass("rounded-lp-pill");
  });
});

describe("Skeleton", () => {
  it("is hidden from assistive technology", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });

  it("is shape matched rather than a circle", () => {
    const { container } = render(<Skeleton shape="page" />);
    const node = container.firstElementChild;
    expect(node).toHaveClass("aspect-[1/1.294]");
    expect(node?.className).not.toContain("rounded-lp-pill");
  });

  it("marks itself so reduced motion can stop the shimmer", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstElementChild).toHaveAttribute("data-lp-shimmer");
  });
});

describe("ProgressRail", () => {
  it("names every stage instead of showing a spinner", () => {
    render(<ProgressRail stages={STAGES} currentIndex={1} label="Generation" />);
    for (const stage of STAGES) {
      expect(screen.getByText(stage.label)).toBeInTheDocument();
    }
  });

  it("announces the stage in flight politely", () => {
    const { container } = render(
      <ProgressRail stages={STAGES} currentIndex={1} label="Generation" />,
    );
    const live = container.querySelector("[aria-live='polite']");
    expect(live).toHaveTextContent("Generation: Tailoring the resume, step 2 of 3");
  });

  it("announces a failure assertively and keeps the stage names on screen", () => {
    render(
      <ProgressRail
        stages={STAGES}
        currentIndex={1}
        status="error"
        errorMessage="The tailoring step failed. Your job description was kept."
        label="Generation"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The tailoring step failed. Your job description was kept.",
    );
    expect(screen.getByText("Tailoring the resume")).toBeInTheDocument();
  });

  it("reports completion", () => {
    const { container } = render(
      <ProgressRail stages={STAGES} currentIndex={2} status="complete" label="Generation" />,
    );
    expect(container.querySelector("[aria-live='polite']")).toHaveTextContent(
      "Generation complete",
    );
  });
});

describe("EmptyState", () => {
  it("says what goes here and offers one action", () => {
    render(
      <EmptyState
        title="No tailored resumes yet"
        description="Paste a job description in Tailor and the result lands here."
        action={<button type="button">Open Tailor</button>}
      />,
    );
    expect(screen.getByText("No tailored resumes yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Tailor" })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("announces itself assertively", () => {
    render(<ErrorState title="The renderer could not build this PDF" />);
    // role="alert" takes no name from its contents, so assert on the text.
    expect(screen.getByRole("alert")).toHaveTextContent("The renderer could not build this PDF");
  });

  it("shows the cause verbatim and selectable", () => {
    const cause = "rendercv: invalid date '2023-13' in section 'experience', entry 2";
    render(<ErrorState title="The renderer could not build this PDF" cause={cause} />);
    const pre = screen.getByText(cause);
    expect(pre.tagName).toBe("PRE");
    expect(pre).toHaveClass("select-text");
  });

  it("offers a retry action", () => {
    render(
      <ErrorState
        title="Could not load the library"
        action={<button type="button">Try again</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
