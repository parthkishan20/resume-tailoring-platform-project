import "../test-polyfills";
import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AlertDialog, AlertDialogContent, AlertDialogTrigger } from "../AlertDialog";
import { Button } from "../Button";
import { Dialog, DialogContent, DialogFooter, DialogTrigger } from "../Dialog";
import { Tooltip, TooltipProvider } from "../Tooltip";
import { ToastHost, useToast } from "../Toast";

describe("Dialog", () => {
  function renderDialog() {
    return render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open rules</Button>
        </DialogTrigger>
        <DialogContent title="Generation rules" description="Applied to every tailored resume.">
          <Button>Inside</Button>
          <DialogFooter>
            <Button variant="primary">Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>,
    );
  }

  it("opens with a titled, described dialog", async () => {
    renderDialog();
    await userEvent.click(screen.getByRole("button", { name: "Open rules" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAccessibleName("Generation rules");
    expect(dialog).toHaveAccessibleDescription("Applied to every tailored resume.");
  });

  it("closes on Escape and restores focus to the trigger", async () => {
    renderDialog();
    const trigger = screen.getByRole("button", { name: "Open rules" });
    await userEvent.click(trigger);
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(trigger).toHaveFocus();
  });

  it("offers a labelled close control", async () => {
    renderDialog();
    await userEvent.click(screen.getByRole("button", { name: "Open rules" }));
    await screen.findByRole("dialog");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});

describe("AlertDialog", () => {
  function renderAlert(onConfirm: () => void) {
    return render(
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="danger">Delete resume</Button>
        </AlertDialogTrigger>
        <AlertDialogContent
          title="Delete this resume?"
          description="The resume and its rendered PDF are removed. This cannot be undone."
          confirmLabel="Delete"
          onConfirm={onConfirm}
        />
      </AlertDialog>,
    );
  }

  it("is an alertdialog, not a second click on the same button", async () => {
    renderAlert(jest.fn());
    await userEvent.click(screen.getByRole("button", { name: "Delete resume" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveAccessibleName("Delete this resume?");
    expect(dialog).toHaveAccessibleDescription(
      "The resume and its rendered PDF are removed. This cannot be undone.",
    );
  });

  it("confirms only when the confirm action is chosen", async () => {
    const onConfirm = jest.fn();
    renderAlert(onConfirm);
    await userEvent.click(screen.getByRole("button", { name: "Delete resume" }));
    await screen.findByRole("alertdialog");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Delete resume" }));
    await screen.findByRole("alertdialog");
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("Tooltip", () => {
  it("appears on focus", async () => {
    render(
      <TooltipProvider delayDuration={0}>
        <Tooltip label="Re-render this resume">
          <Button>Render</Button>
        </Tooltip>
      </TooltipProvider>,
    );
    await userEvent.tab();
    expect(await screen.findAllByText("Re-render this resume")).not.toHaveLength(0);
  });
});

describe("Toast", () => {
  function Trigger() {
    const { toast } = useToast();
    return (
      <Button
        onClick={() => {
          toast({ title: "Resume saved", description: "Master resume, just now." });
        }}
      >
        Save
      </Button>
    );
  }

  it("shows a transient result and lets it be dismissed", async () => {
    render(
      <ToastHost>
        <Trigger />
      </ToastHost>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Resume saved")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => {
      expect(screen.queryByText("Resume saved")).not.toBeInTheDocument();
    });
  });

  it("throws rather than silently swallowing a message outside a host", () => {
    const consoleError = jest.spyOn(console, "error").mockImplementation(() => undefined);
    function Orphan() {
      useToast();
      return null;
    }
    expect(() => render(<Orphan />)).toThrow("useToast must be used inside a ToastHost");
    consoleError.mockRestore();
  });
});
