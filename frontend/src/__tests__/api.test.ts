import { api, ApiError } from "@/lib/api";

/** Minimal stand-in for the parts of Response that `request` touches. */
function mockResponse(status: number, body = "", statusText = "") {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: async () => JSON.parse(body),
    text: async () => body,
  } as unknown as Response;
}

const fetchMock = jest.fn();
global.fetch = fetchMock as unknown as typeof fetch;

beforeEach(() => {
  fetchMock.mockReset();
});

// ── 204 and empty bodies (D-31) ──────────────────────────────────────────────

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

test("a 200 with an empty body resolves instead of throwing", async () => {
  fetchMock.mockResolvedValue(mockResponse(200, ""));
  await expect(api.getRules()).resolves.toBeUndefined();
});

test("a 200 with a JSON body is still parsed", async () => {
  const resume = { id: 1, user_id: "default", yaml_content: "cv: {}", updated_at: "2026-01-01" };
  fetchMock.mockResolvedValue(mockResponse(200, JSON.stringify(resume)));
  await expect(api.getMasterResume()).resolves.toEqual(resume);
});

// ── getMasterResume narrowing (D-32) ─────────────────────────────────────────

test("getMasterResume maps a 404 to null", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(404, JSON.stringify({ detail: "No master resume found" }), "Not Found")
  );
  await expect(api.getMasterResume()).resolves.toBeNull();
});

test("getMasterResume surfaces a 500 rather than reporting no resume", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(500, JSON.stringify({ error: "database is locked", code: "DB_ERROR" }))
  );
  await expect(api.getMasterResume()).rejects.toThrow("database is locked");
});

test("getMasterResume surfaces a 503", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(503, JSON.stringify({ error: "provider unavailable", code: "LLM_UNAVAILABLE" }))
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

// ── Error envelopes (D-42) ───────────────────────────────────────────────────

test("an HTTPException {detail} body reaches the caller", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(404, JSON.stringify({ detail: "Resume not found" }), "Not Found")
  );
  await expect(api.getResume(3)).rejects.toThrow("Resume not found");
});

test("a custom handler {error, code} body reaches the caller with its code", async () => {
  fetchMock.mockResolvedValue(
    mockResponse(500, JSON.stringify({ error: "rendercv exited 1", code: "RENDER_FAILED" }))
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

test("a 422 whose detail is not a string falls back to the status text", async () => {
  const detail = [{ loc: ["body", "yaml_content"], msg: "field required" }];
  fetchMock.mockResolvedValue(
    mockResponse(422, JSON.stringify({ detail }), "Unprocessable Entity")
  );
  await expect(api.saveMasterResume("cv: {}")).rejects.toThrow("Unprocessable Entity");
});

test("an unparseable error body falls back to the status", async () => {
  fetchMock.mockResolvedValue(mockResponse(502, "<html>bad gateway</html>"));
  await expect(api.getResume(1)).rejects.toThrow("Request failed (502)");
});
