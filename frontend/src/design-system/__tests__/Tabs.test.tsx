import "../test-polyfills";
import * as React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../Tabs";

function renderTabs() {
  return render(
    <Tabs defaultValue="tailor">
      <TabsList aria-label="Inspector">
        <TabsTrigger value="tailor">Tailor</TabsTrigger>
        <TabsTrigger value="evaluate">Evaluate</TabsTrigger>
        <TabsTrigger value="assistant">Assistant</TabsTrigger>
      </TabsList>
      <TabsContent value="tailor">Tailor panel</TabsContent>
      <TabsContent value="evaluate">Evaluate panel</TabsContent>
      <TabsContent value="assistant">Assistant panel</TabsContent>
    </Tabs>,
  );
}

describe("Tabs", () => {
  it("renders the real tab contract, not bare role=tab", () => {
    renderTabs();
    expect(screen.getByRole("tablist", { name: "Inspector" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Tailor panel");
  });

  it("uses a roving tabindex: one tab stop for the whole list", async () => {
    renderTabs();
    await userEvent.tab();
    expect(screen.getByRole("tab", { name: "Tailor" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Evaluate" })).toHaveAttribute("tabindex", "-1");
  });

  it("moves between tabs with the arrow keys", async () => {
    renderTabs();
    await userEvent.tab();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Evaluate" })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Evaluate panel");
  });

  it("jumps to the ends with Home and End", async () => {
    renderTabs();
    await userEvent.tab();
    await userEvent.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Assistant" })).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Tailor" })).toHaveFocus();
  });

  it("marks the selected tab with aria-selected", async () => {
    renderTabs();
    await userEvent.click(screen.getByRole("tab", { name: "Assistant" }));
    expect(screen.getByRole("tab", { name: "Assistant" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Tailor" })).toHaveAttribute("aria-selected", "false");
  });
});
