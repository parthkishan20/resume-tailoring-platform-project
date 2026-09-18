import "../test-polyfills";
import * as React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IconButton } from "../IconButton";
import { TooltipProvider } from "../Tooltip";

function renderIconButton(props: Partial<React.ComponentProps<typeof IconButton>> = {}) {
  return render(
    <TooltipProvider delayDuration={0}>
      <IconButton label="Download PDF" icon={<span>icon</span>} {...props} />
    </TooltipProvider>,
  );
}

describe("IconButton", () => {
  it("exposes the label as the accessible name", () => {
    renderIconButton();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeInTheDocument();
  });

  it("hides the icon from assistive technology so the name is not doubled", () => {
    renderIconButton();
    expect(screen.getByText("icon").closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("shows its tooltip on keyboard focus, not only on hover", async () => {
    renderIconButton();
    await userEvent.tab();
    expect(await screen.findAllByText("Download PDF")).not.toHaveLength(0);
  });

  it("is reachable by keyboard and activates on Enter", async () => {
    const onClick = jest.fn();
    renderIconButton({ onClick });
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Download PDF" })).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
