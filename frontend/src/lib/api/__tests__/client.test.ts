/**
 * The typed client at the fetch boundary.
 *
 * Moved from `src/__tests__/api.test.ts` when task 2.2 replaced the module it
 * tested, and colocated with what it covers. Every assertion in that file is
 * still here except two, which pinned behaviour this task deliberately
 * changed; both are kept as tests of the new behaviour, with the old
 * expectation named so the change is visible rather than quietly dropped.
 */

import { api, ApiError, CLIENT_ERROR_CODES, abortable, hasCode } from "@/lib/api";

/** The parts of `Response` the request path touches. */
function mockResponse(status: number, body = "", statusText = "") {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: async () => JSON.parse(body) as unknown,
    text: async () => body,
  } as unknown as Response;
}

const MASTER_RESUME = {
  id: 1,
  user_id: "default",
  yaml_content: "cv: {}",
  updated_at: "2026-01-01T00:00:00Z",
};

const fetchMock = jest.fn();
global.fetch = fetchMock as unknown as typeof fetch;

beforeEach(() => {
  fetchMock.mockReset();
});

// -- 204 and empty bodies (D-31) -------------------------------------------

test("deleteMasterResume resolves on a 204 instead of throwing", async () => {
  fetchMock.mockResolvedValue(mockResponse(204));
  await expect(api.deleteMasterResume()).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledWith("/api/master-resume", { method: "DELETE" });
});

test("deleteResume resolves on a 204", async () => {
  fetchMock.mockResolvedValue(mockResponse(204));
  await expect(api.deleteResume(7)).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledWith("/api/resumes/7", { method: "DELETE" });
});

test("clearChat resolves on a 204", async () => {
  fetchMock.mockResolvedValue(mockResponse(204));
  await expect(api.clearChat()).resolves.toBeUndefined();
  expect(fetchMock).toHaveBeenCalledWith("/api/chat", { method: "DELETE" });
});

test("a 200 with a JSON body is still parsed", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify(MASTER_RESUME)));
  await expect(api.getMasterResume()).resolves.toEqual(MASTER_RESUME);
});

// -- responses are validated, not cast (D-60) ------------------------------

test("a 200 with an empty body is a contract violation, not an empty result", async () => {
  // The old client returned `undefined` here, typed as `Rule[]`, and the
  // caller found out by indexing into it. `GET /api/rules` is declared to
  // return a list, so an empty body is the server breaking its contract and
  // the client says so at the boundary.
  fetchMock.mockResolvedValue(mockResponse(200, ""));
  await expect(api.getRules()).rejects.toMatchObject({
    code: CLIENT_ERROR_CODES.invalidShape,
  });
});

test("a body missing a declared field is rejected", async () => {
  const { yaml_content: _dropped, ...withoutYaml } = MASTER_RESUME;
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify(withoutYaml)));
  await expect(api.getMasterResume()).rejects.toMatchObject({
    code: CLIENT_ERROR_CODES.invalidShape,
  });
});

test("a body with the wrong type for a declared field is rejected", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify({ ...MASTER_RESUME, id: "one" })));
  await expect(api.getMasterResume()).rejects.toBeInstanceOf(ApiError);
});

test("an extra field the client has not heard of is accepted and dropped", async () => {
  // A server newer than the tab must not break it. The declared fields are
  // required; anything else is ignored rather than rejected.
  fetchMock.mockResolvedValue(
    mockResponse(200, JSON.stringify({ ...MASTER_RESUME, theme: "classic" })),
  );
  await expect(api.getMasterResume()).resolves.toEqual(MASTER_RESUME);
});

test("a 200 that is not this API at all is rejected", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, "<html>captive portal</html>"));
  await expect(api.getRules()).rejects.toMatchObject({
    code: CLIENT_ERROR_CODES.invalidShape,
  });
});

// -- getMasterResume narrowing (D-32) --------------------------------------

test("getMasterResume maps a 404 to null", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(404, JSON.stringify({ detail: "No master resume found" }), "Not Found"),
  );
  await expect(api.getMasterResume()).resolves.toBeNull();
});

test("getMasterResume surfaces a 500 rather than reporting no resume", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(500, JSON.stringify({ error: "database is locked", code: "DB_ERROR" })),
  );
  await expect(api.getMasterResume()).rejects.toThrow("database is locked");
});

test("getMasterResume surfaces a 503", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(503, JSON.stringify({ error: "provider unavailable", code: "LLM_UNAVAILABLE" })),
  );
  await expect(api.getMasterResume()).rejects.toMatchObject({
    status: 503,
    code: "LLM_UNAVAILABLE",
  });
});

test("getMasterResume surfaces a network failure", async () => {
  fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
  await expect(api.getMasterResume()).rejects.toThrow("Failed to fetch");
});

test("a network failure carries the transport code", async () => {
  fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
  await expect(api.getResume(1)).rejects.toMatchObject({
    status: 0,
    code: CLIENT_ERROR_CODES.network,
  });
});

// -- error envelopes (D-42) ------------------------------------------------

test("an HTTPException {detail} body reaches the caller", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(404, JSON.stringify({ detail: "Resume not found" }), "Not Found"),
  );
  await expect(api.getResume(3)).rejects.toThrow("Resume not found");
});

test("a custom handler {error, code} body reaches the caller with its code", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(500, JSON.stringify({ error: "rendercv exited 1", code: "RENDER_FAILED" })),
  );
  await expect(api.renderResume(3)).rejects.toMatchObject({
    name: "ApiError",
    message: "rendercv exited 1",
    status: 500,
    code: "RENDER_FAILED",
  });
});

test("thrown errors are ApiError instances", async () => {
  fetchMock.mockResolvedValue(mockResponse(500, JSON.stringify({ error: "boom" })));
  await expect(api.getResume(1)).rejects.toBeInstanceOf(ApiError);
});

test("a 422 whose detail is an array becomes one line naming each field", async () => {
  // The old client ignored an array `detail` and showed the status text, which
  // is the half of D-42 the user actually saw: "Unprocessable Entity" instead
  // of which field was wrong.
  const detail = [{ loc: ["body", "yaml_content"], msg: "field required" }];
  fetchMock.mockResolvedValue(
    mockResponse(422, JSON.stringify({ detail }), "Unprocessable Entity"),
  );
  await expect(api.saveMasterResume("cv: {}")).rejects.toThrow("body.yaml_content: field required");
});

test("several validation issues are all reported", async () => {
  const detail = [
    { loc: ["query", "limit"], msg: "less than or equal to 100" },
    { loc: ["query", "page"], msg: "greater than or equal to 1" },
  ];
  fetchMock.mockResolvedValue(mockResponse(422, JSON.stringify({ detail })));
  await expect(api.listResumes()).rejects.toThrow(
    "query.limit: less than or equal to 100; query.page: greater than or equal to 1",
  );
});

test("an unparseable error body falls back to the status", async () => {
  fetchMock.mockResolvedValue(mockResponse(502, "<html>bad gateway</html>"));
  await expect(api.getResume(1)).rejects.toThrow("Request failed (502)");
});

test("hasCode matches only the code that arrived", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(503, JSON.stringify({ error: "down", code: "LLM_UNAVAILABLE" })),
  );
  const error = await api.getResume(1).catch((cause: unknown) => cause);
  expect(hasCode(error, "LLM_UNAVAILABLE")).toBe(true);
  expect(hasCode(error, "RENDER_FAILED")).toBe(false);
});

// -- cancellation (D-40) ---------------------------------------------------

test("the caller's signal reaches fetch", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify(MASTER_RESUME)));
  const { signal } = abortable();
  await api.getMasterResume({ signal });
  expect(fetchMock).toHaveBeenCalledWith("/api/master-resume", { method: "GET", signal });
});

test("every request-issuing function accepts a signal", async () => {
  fetchMock.mockResolvedValue(mockResponse(204));
  const { signal } = abortable();
  await api.deleteResume(4, { signal });
  expect(fetchMock).toHaveBeenCalledWith("/api/resumes/4", { method: "DELETE", signal });
});

test("a signal on a request with a JSON body is forwarded too", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify(MASTER_RESUME)));
  const { signal } = abortable();
  await api.saveMasterResume("cv: {}", { signal });
  expect(fetchMock).toHaveBeenCalledWith("/api/master-resume", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml_content: "cv: {}" }),
    signal,
  });
});

test("an abort is not turned into an ApiError", async () => {
  // Every error boundary, and TanStack Query, recognises an AbortError by
  // name. Wrapping it would make a cancelled request look like a failed one.
  fetchMock.mockRejectedValue(new DOMException("The operation was aborted.", "AbortError"));
  const error = await api.getResume(1).catch((cause: unknown) => cause);
  expect(error).not.toBeInstanceOf(ApiError);
  expect((error as DOMException).name).toBe("AbortError");
});

test("cancel() aborts the signal it handed out", () => {
  const { signal, cancel } = abortable();
  expect(signal.aborted).toBe(false);
  cancel();
  expect(signal.aborted).toBe(true);
});

// -- pagination (D-10) -----------------------------------------------------

test("listResumes sends the bounded parameters the route declares", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(200, JSON.stringify({ items: [], total: 0, page: 2, limit: 20 })),
  );
  await api.listResumes("jd", "asc", 2);
  expect(fetchMock).toHaveBeenCalledWith("/api/resumes?sort=jd&order=asc&page=2&limit=20", {
    method: "GET",
  });
});

test("a library page is validated, list rows included", async () => {
  const page = {
    items: [
      {
        id: 3,
        user_id: "default",
        name: "Senior Engineer",
        job_description: "jd",
        pdf_path: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    total: 1,
    page: 1,
    limit: 20,
  };
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify(page)));
  await expect(api.listResumes()).resolves.toEqual(page);
});

test("a library page whose rows are the wrong shape is rejected", async () => {
  const page = { items: [{ id: 3 }], total: 1, page: 1, limit: 20 };
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify(page)));
  await expect(api.listResumes()).rejects.toMatchObject({
    code: CLIENT_ERROR_CODES.invalidShape,
  });
});

// -- chat pagination (B-07, D-21) -------------------------------------------

test("getChatHistory with no params fetches the whole transcript, unbounded", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, "[]"));
  await api.getChatHistory();
  expect(fetchMock).toHaveBeenCalledWith("/api/chat", { method: "GET" });
});

test("getChatHistory sends limit and before_id as a bounded, paged request", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, "[]"));
  await api.getChatHistory({ limit: 30, beforeId: 16 });
  expect(fetchMock).toHaveBeenCalledWith("/api/chat?limit=30&before_id=16", { method: "GET" });
});
