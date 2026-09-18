import { defineConfig, devices } from "@playwright/test";

/**
 * BASE_URL is required. It is never defaulted.
 *
 * Every spec's `beforeEach` issues destructive calls (DELETE /api/master-resume,
 * DELETE /api/chat, DELETE /api/rules, PUT /api/master-resume). A default would
 * silently point those at whatever answers on that address — and the dev stack
 * binds localhost:8000 with a live API key and the user's real resume. So the
 * suite refuses to guess, and refuses a loopback address on the dev port.
 *
 * Run the suite with scripts/run_e2e.sh, which starts the isolated test stack
 * and exports the right BASE_URL.
 */
function resolveBaseURL(): string {
  const raw = process.env.BASE_URL?.trim();

  if (!raw) {
    throw new Error(
      "BASE_URL is not set.\n" +
        "The e2e suite deletes and overwrites data on whatever it is pointed at, " +
        "so it will not guess an address.\n" +
        "Run the whole isolated stack instead:  ./scripts/run_e2e.sh\n" +
        "Or point it at an already-running test stack:  " +
        "BASE_URL=http://localhost:18173 npx playwright test",
    );
  }

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`BASE_URL is not a valid URL: ${raw}`);
  }

  const isLoopback = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"].includes(
    url.hostname,
  );
  const port = url.port || (url.protocol === "https:" ? "443" : "80");

  if (isLoopback && port === "8000") {
    throw new Error(
      `BASE_URL is ${raw}, which is the dev/production stack.\n` +
        "docker-compose.yml and scripts/start_mac.sh bind host port 8000 to a " +
        "container holding your real resume data and a live API key.\n" +
        "The e2e suite would delete it. Use the isolated test stack: ./scripts/run_e2e.sh",
    );
  }

  return raw;
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 1,
  timeout: 30_000,
  use: {
    baseURL: resolveBaseURL(),
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  reporter: [["list"], ["html", { open: "never" }]],
});
