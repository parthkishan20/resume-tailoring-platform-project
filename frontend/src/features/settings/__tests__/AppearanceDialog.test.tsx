import "@/design-system/test-polyfills";
import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider } from "next-themes";
import "@testing-library/jest-dom";
import { AppearanceDialog } from "../AppearanceDialog";
import { TooltipProvider } from "@/design-system";
import "@/features/test-harness";

function Harness({ defaultTheme = "light" }: { defaultTheme?: string }) {
  const [open, setOpen] = React.useState(true);
  return (
    <ThemeProvider attribute="data-theme" defaultTheme={defaultTheme} enableColorScheme={false}>
      <TooltipProvider>
        <AppearanceDialog open={open} onOpenChange={setOpen} />
      </TooltipProvider>
    </ThemeProvider>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.className = "";
});

/**
 * D-11 end to end, as far as jsdom reaches: the control writes `data-theme`
 * onto the root element, which is the attribute `tokens.css` keys the whole
 * dark swap off. `layout.tsx` no longer hardcodes `className="dark"`, so this
 * is the only thing choosing a theme.
 */
describe("the theme toggle actually toggles", () => {
  test("choosing Dark writes data-theme=dark onto the root element", async () => {
    render(<Harness />);

    fireEvent.click(screen.getByTestId("theme-dark"));

    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
  });

  test("choosing Light writes it back", async () => {
    render(<Harness defaultTheme="dark" />);

    fireEvent.click(screen.getByTestId("theme-light"));

    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "light"));
  });

  test("System resolves through prefers-color-scheme rather than a stored value", async () => {
    render(<Harness />);

    fireEvent.click(screen.getByTestId("theme-system"));

    // The harness answers "no match" to every media query, so system resolves
    // to light: light is the base token definition, per 2.1.
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "light"));
  });

  test("the chosen theme is announced as selected, not only coloured", async () => {
    render(<Harness />);

    await waitFor(() =>
      expect(screen.getByTestId("theme-light")).toHaveAttribute("aria-checked", "true"),
    );
    expect(screen.getByTestId("theme-dark")).toHaveAttribute("aria-checked", "false");

    fireEvent.click(screen.getByTestId("theme-dark"));

    await waitFor(() =>
      expect(screen.getByTestId("theme-dark")).toHaveAttribute("aria-checked", "true"),
    );
  });

  test("the three choices form one radio group", () => {
    render(<Harness />);
    const group = screen.getByRole("radiogroup", { name: "Theme" });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });
});
