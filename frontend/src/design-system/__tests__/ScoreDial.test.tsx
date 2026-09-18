import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ScoreDial } from "@/design-system";

describe("ScoreDial", () => {
  test("carries the numeral and the band label in one accessible sentence", () => {
    render(<ScoreDial score={82} />);
    expect(screen.getByTestId("score-dial")).toHaveAttribute(
      "aria-label",
      "Match score 82 out of 100. Strong match.",
    );
  });

  // Section 5: "never by colour alone". The ring is `aria-hidden`, so the
  // numeral and band label are the two channels a screen reader gets, and
  // both are visible text, not colour.
  test("shows the numeral and band label as visible text, not only as colour", () => {
    render(<ScoreDial score={40} />);
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("Weak match")).toBeInTheDocument();
  });

  test.each([
    [90, "Strong match"],
    [75, "Strong match"],
    [74, "Partial match"],
    [50, "Partial match"],
    [49, "Weak match"],
    [0, "Weak match"],
  ])("bands score %i as %s", (score, label) => {
    render(<ScoreDial score={score} />);
    expect(screen.getByTestId("score-dial")).toHaveAttribute(
      "aria-label",
      expect.stringContaining(label),
    );
  });

  test("clamps an out-of-range score rather than drawing off the ring", () => {
    render(<ScoreDial score={140} />);
    expect(screen.getByTestId("score-dial")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("Match score 100 out of 100"),
    );
  });

  test("the ring draws in on mount rather than painting at its final position", async () => {
    render(<ScoreDial score={60} />);
    const offset = () =>
      screen
        .getByTestId("score-dial")
        .querySelectorAll("circle")[1]
        .getAttribute("stroke-dashoffset");

    // Before the first animation frame, the ring is at full circumference
    // (fully hidden): draw-in has a `from`, not just a `to` (2.7: 700ms
    // ease-out, once).
    expect(offset()).toBe("238.76104167282426");

    // A frame later, it has moved to the value the 60% score actually draws.
    await waitFor(() => expect(offset()).not.toBe("238.76104167282426"));
  });

  test("is round-tripped through role=img rather than exposing the SVG to the tree", () => {
    render(<ScoreDial score={60} />);
    expect(screen.getByRole("img", { name: /Match score 60 out of 100/ })).toBeInTheDocument();
  });
});
