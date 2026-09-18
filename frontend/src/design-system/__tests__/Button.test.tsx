import "../test-polyfills";
import * as React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "../Button";

describe("Button", () => {
  it("renders its label and fires onClick", async () => {
    const onClick = jest.fn();
    render(<Button onClick={onClick}>Save resume</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Save resume" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("keeps the label in the DOM while loading so the width does not jump", () => {
    const { rerender } = render(<Button>Generate</Button>);
    const idleWidthSource = screen.getByRole("button").textContent;

    rerender(
      <Button loading loadingLabel="Generating">
        Generate
      </Button>,
    );
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
    // The label is still rendered, just visually hidden.
    expect(button.textContent).toContain(idleWidthSource ?? "");
    expect(screen.getByText("Generating")).toHaveClass("sr-only");
  });

  it("does not fire onClick while loading or disabled", async () => {
    const onClick = jest.fn();
    const { rerender } = render(
      <Button loading onClick={onClick}>
        Generate
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    rerender(
      <Button disabled onClick={onClick}>
        Generate
      </Button>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Cancel</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("renders every variant", () => {
    for (const variant of ["primary", "secondary", "ghost", "danger"] as const) {
      const { unmount } = render(<Button variant={variant}>{variant}</Button>);
      expect(screen.getByRole("button", { name: variant })).toBeInTheDocument();
      unmount();
    }
  });
});
