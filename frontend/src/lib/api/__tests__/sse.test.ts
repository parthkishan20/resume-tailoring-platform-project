/**
 * The streaming readers: frames parsed, frames validated, stream released.
 *
 * The three things being pinned are the three the old reader did not do:
 * release the response body when the consumer stops reading, carry a signal,
 * and validate a frame instead of letting the call site cast it.
 */

import { TextDecoder, TextEncoder } from "util";

import { CLIENT_ERROR_CODES, readSseStream, streamChat, streamTailor } from "@/lib/api";

// jsdom ships neither, and the reader decodes every chunk. Node's are the same
// implementation the browser has; this only puts them where jsdom left a hole.
Object.assign(globalThis, { TextDecoder, TextEncoder });

const ENCODER = new TextEncoder();

interface StreamHandle {
  response: Response;
  cancelled: () => boolean;
}

/** A `Response` whose body yields `chunks` and records being cancelled. */
function sseResponse(chunks: string[], status = 200): StreamHandle {
  let cancelled = false;
  let index = 0;
  const reader = {
    read: async () =>
      index < chunks.length
        ? { done: false, value: ENCODER.encode(chunks[index++]) }
        : { done: true, value: undefined },
    cancel: async () => {
      cancelled = true;
    },
  };
  const response = {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    body: { getReader: () => reader },
    json: async () => ({}),
    text: async () => "",
  } as unknown as Response;
  return { response, cancelled: () => cancelled };
}

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

const STORED_RESUME = {
  id: 9,
  user_id: "default",
  name: "Senior Engineer",
  job_description: "jd",
  yaml_content: "cv: {}",
  pdf_path: "9.pdf",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const fetchMock = jest.fn();
global.fetch = fetchMock as unknown as typeof fetch;

beforeEach(() => {
  fetchMock.mockReset();
});

// -- the untyped reader, which the un-migrated panels still use -------------

test("readSseStream yields one event per frame, in order", async () => {
  const { response } = sseResponse([
    frame("progress", { message: "Analyzing job description..." }),
    frame("done", { result: STORED_RESUME }),
  ]);
  fetchMock.mockResolvedValue(response);

  const seen: string[] = [];
  for await (const event of readSseStream("/api/resumes/stream", { job_description: "jd" })) {
    seen.push(event.event);
  }
  expect(seen).toEqual(["progress", "done"]);
});

test("a frame split across two chunks is still one event", async () => {
  const whole = frame("progress", { message: "Rendering PDF..." });
  const { response } = sseResponse([whole.slice(0, 12), whole.slice(12)]);
  fetchMock.mockResolvedValue(response);

  const events = [];
  for await (const event of readSseStream("/api/chat/stream", {})) events.push(event);
  expect(events).toEqual([{ event: "progress", data: { message: "Rendering PDF..." } }]);
});

test("the response body is released when the consumer stops early", async () => {
  const { response, cancelled } = sseResponse([
    frame("token", { delta: "a" }),
    frame("token", { delta: "b" }),
    frame("token", { delta: "c" }),
  ]);
  fetchMock.mockResolvedValue(response);

  for await (const _event of readSseStream("/api/chat/stream", { message: "hi" })) {
    break;
  }
  expect(cancelled()).toBe(true);
});

test("the response body is released when the stream ends normally", async () => {
  const { response, cancelled } = sseResponse([frame("token", { delta: "a" })]);
  fetchMock.mockResolvedValue(response);

  for await (const _event of readSseStream("/api/chat/stream", { message: "hi" })) {
    // drain
  }
  expect(cancelled()).toBe(true);
});

test("a status before the stream starts becomes an ApiError", async () => {
  // The only way a streaming route answers a status is refusing the request
  // outright: a 413, a 429, or a 422 on the body. Once the generator runs the
  // status is 200 whatever happens (D-55).
  const failed = {
    ok: false,
    status: 429,
    statusText: "Too Many Requests",
    body: null,
    json: async () => ({ error: "Too many requests.", code: "RATE_LIMITED" }),
    text: async () => "",
  } as unknown as Response;
  fetchMock.mockResolvedValue(failed);

  const iterator = readSseStream("/api/chat/stream", { message: "hi" });
  await expect(iterator.next()).rejects.toMatchObject({
    status: 429,
    code: "RATE_LIMITED",
  });
});

// -- the typed readers -----------------------------------------------------

test("streamTailor validates and narrows each frame", async () => {
  const { response } = sseResponse([
    frame("progress", { message: "Tailoring content..." }),
    frame("done", { result: STORED_RESUME }),
  ]);
  fetchMock.mockResolvedValue(response);

  const collected: string[] = [];
  for await (const event of streamTailor({ job_description: "jd" })) {
    if (event.event === "progress") collected.push(event.data.message);
    if (event.event === "done") collected.push(event.data.result.name);
  }
  expect(collected).toEqual(["Tailoring content...", "Senior Engineer"]);
});

test("streamTailor rejects a done frame that is not a stored resume", async () => {
  const { response } = sseResponse([frame("done", { result: { id: 9 } })]);
  fetchMock.mockResolvedValue(response);

  const iterator = streamTailor({ job_description: "jd" });
  await expect(iterator.next()).rejects.toMatchObject({
    code: CLIENT_ERROR_CODES.invalidShape,
  });
});

test("an error frame carries the code the exception raised", async () => {
  // The three routes emit `exc.code` as of task 2.2, so a subclass no longer
  // arrives under its base class's code.
  const { response } = sseResponse([
    frame("error", { error: "The provider answered with nothing.", code: "LLM_EMPTY_RESPONSE" }),
  ]);
  fetchMock.mockResolvedValue(response);

  const frames = [];
  for await (const event of streamChat({ message: "hi" })) frames.push(event);
  expect(frames).toEqual([
    {
      event: "error",
      data: { error: "The provider answered with nothing.", code: "LLM_EMPTY_RESPONSE" },
    },
  ]);
});

test("an event name the contract does not declare is an error, not a silent skip", async () => {
  // Dropping an unrecognised frame would let a misspelled `done` hang a panel
  // on its spinner for as long as the user is willing to wait.
  const { response } = sseResponse([frame("finished", { result: STORED_RESUME })]);
  fetchMock.mockResolvedValue(response);

  const iterator = streamTailor({ job_description: "jd" });
  await expect(iterator.next()).rejects.toMatchObject({
    code: CLIENT_ERROR_CODES.invalidShape,
  });
});

test("a typed reader forwards the caller's signal", async () => {
  const { response } = sseResponse([frame("token", { delta: "a" })]);
  fetchMock.mockResolvedValue(response);
  const controller = new AbortController();

  for await (const _event of streamChat({ message: "hi" }, { signal: controller.signal })) {
    // drain
  }
  expect(fetchMock).toHaveBeenCalledWith("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "hi" }),
    signal: controller.signal,
  });
});
