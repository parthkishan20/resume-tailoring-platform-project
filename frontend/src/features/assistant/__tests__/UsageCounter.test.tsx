import "@/design-system/test-polyfills";
import { screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { renderInWorkspace } from "@/features/test-harness";
import { api } from "@/lib/api";
import { UsageCounter } from "../UsageCounter";

jest.mock("@/lib/api", () => ({
  ApiError: jest.requireActual("@/lib/api").ApiError,
  api: {
    getLlmUsage: jest.fn(),
  },
}));

const getLlmUsage = api.getLlmUsage as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
});

test("renders nothing before the first poll resolves", () => {
  getLlmUsage.mockReturnValue(new Promise(() => {})); // never resolves
  renderInWorkspace(<UsageCounter />);
  expect(screen.queryByTestId("llm-usage-counter")).not.toBeInTheDocument();
});

test("shows both windows once the counts arrive", async () => {
  getLlmUsage.mockResolvedValue({
    minute_count: 3,
    minute_limit: 20,
    day_count: 12,
    day_limit: 50,
  });
  renderInWorkspace(<UsageCounter />);

  const chip = await screen.findByTestId("llm-usage-counter");
  expect(chip).toHaveTextContent("3/20");
  expect(chip).toHaveTextContent("12/50");
});

test("reads as critical once either window is near its limit", async () => {
  getLlmUsage.mockResolvedValue({
    minute_count: 17,
    minute_limit: 20,
    day_count: 12,
    day_limit: 50,
  });
  renderInWorkspace(<UsageCounter />);

  const chip = await screen.findByTestId("llm-usage-counter");
  await waitFor(() => expect(chip.className).toMatch(/critical/));
});

test("stays neutral when both windows have headroom", async () => {
  getLlmUsage.mockResolvedValue({
    minute_count: 1,
    minute_limit: 20,
    day_count: 2,
    day_limit: 50,
  });
  renderInWorkspace(<UsageCounter />);

  const chip = await screen.findByTestId("llm-usage-counter");
  expect(chip.className).not.toMatch(/critical/);
});
