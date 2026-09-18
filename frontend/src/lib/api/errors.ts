/**
 * One typed error for every way a request can fail. D-42.
 *
 * The old client read `detail` and `error` and kept `code`, which was the
 * client half of D-42 and is preserved here. What it could not do is tell the
 * UI *which* failure happened: `code` was `string | undefined`, so
 * `err.code === "LLM_ATUH_ERROR"` compiled and never matched, and there was
 * nowhere to look up what the server can actually send.
 *
 * The vocabulary now comes from the server. `ErrorCode` is generated from the
 * OpenAPI document, which builds it from the exception classes themselves
 * (`api/schemas/errors.py`), so a code added on the backend appears in this
 * union as soon as the types are regenerated, and a typo in a comparison is a
 * compile error. Use {@link hasCode} to get that checking.
 *
 * The runtime value stays a plain `string`, deliberately. A server newer than
 * the browser tab can send a code this build has never heard of, and the right
 * behaviour then is to show the message and carry on, not to throw.
 */

import type { components } from "./generated/schema";

/** Every `code` the server can send. Generated; see the module comment. */
export type ErrorCode = components["schemas"]["ErrorCode"];

/**
 * Failures that happen in the browser and never came from the server.
 *
 * Kept separate from {@link ErrorCode} so the two can never be confused: a
 * `RESPONSE_SHAPE_INVALID` means this client and that server disagree about
 * the contract, which is a bug to fix rather than a state to handle.
 */
export const CLIENT_ERROR_CODES = {
  /** `fetch` itself rejected: offline, DNS, TLS, connection reset. */
  network: "NETWORK_ERROR",
  /** The body parsed as JSON but did not match the schema for this route. */
  invalidShape: "RESPONSE_SHAPE_INVALID",
} as const;

export type ClientErrorCode = (typeof CLIENT_ERROR_CODES)[keyof typeof CLIENT_ERROR_CODES];

/**
 * Anything that came back instead of the response that was asked for.
 *
 * `status` is the HTTP status, or 0 when there was no response at all.
 * `message` is always safe to show a user: on the server's side it is a fixed
 * sentence per error class and never the text of an exception (D-53).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/**
 * `true` when `error` is an {@link ApiError} carrying exactly `code`.
 *
 * The point is the parameter type: `code` must be one the server declares, so
 * a misspelled branch does not compile. Pass a {@link ClientErrorCode} to test
 * for one of the browser-side failures instead.
 */
export function hasCode(error: unknown, code: ErrorCode | ClientErrorCode): boolean {
  return error instanceof ApiError && error.code === code;
}

/** `true` when the caller cancelled this request rather than it failing. */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/**
 * The three error bodies this API produces, read into one message and code.
 *
 * `{error, code}` is the application envelope and the only shape with a code.
 * `{detail: "..."}` is an `HTTPException` from a route. `{detail: [...]}` is
 * FastAPI's own validation failure, and its entries are joined into one line
 * with the field each names, because "body.yaml_content: field required" is
 * usable and "Unprocessable Entity" is not. See `api/schemas/errors.py` for
 * why there are three and not one.
 */
function readErrorBody(body: unknown): { message: string | null; code?: string } {
  if (body === null || typeof body !== "object") return { message: null };
  const record = body as Record<string, unknown>;

  const envelope = asString(record.error);
  if (envelope !== null) {
    return { message: envelope, code: asString(record.code) ?? undefined };
  }

  const detail = record.detail;
  const sentence = asString(detail);
  if (sentence !== null) return { message: sentence };

  if (Array.isArray(detail)) {
    const lines = detail
      .map((issue) => {
        if (issue === null || typeof issue !== "object") return null;
        const entry = issue as Record<string, unknown>;
        const msg = asString(entry.msg);
        if (msg === null) return null;
        const where = Array.isArray(entry.loc) ? entry.loc.join(".") : null;
        return where === null ? msg : `${where}: ${msg}`;
      })
      .filter((line): line is string => line !== null);
    if (lines.length > 0) return { message: lines.join("; ") };
  }

  return { message: null };
}

/**
 * Turn a failed `Response` into an {@link ApiError}.
 *
 * Reading the body can itself fail (an empty 502 from a proxy, a truncated
 * stream), which is why the status line is the fallback and never the other
 * way round: a client that throws while building an error message loses the
 * original failure.
 */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let parsed: unknown = null;
  try {
    parsed = await response.json();
  } catch {
    parsed = null;
  }
  const { message, code } = readErrorBody(parsed);
  // `||` on the status text, not `??`: a proxy that sends no reason phrase
  // gives an empty string, not `undefined`, and "" is not a message.
  return new ApiError(
    message ?? (response.statusText || `Request failed (${response.status})`),
    response.status,
    code,
  );
}

/**
 * Wrap whatever `fetch` rejected with, unless the caller cancelled.
 *
 * An `AbortError` is passed through untouched on purpose: it is not a failure,
 * and TanStack Query, React and the SSE readers all recognise it by name.
 * Turning it into an `ApiError` would make a cancelled request look like a
 * failed one in every error boundary in the app.
 */
export function errorFromTransport(cause: unknown): unknown {
  if (isAbortError(cause)) return cause;
  const message = cause instanceof Error ? cause.message : "The request could not be sent.";
  return new ApiError(message, 0, CLIENT_ERROR_CODES.network);
}

/**
 * The body arrived and did not match this route's schema.
 *
 * The user-facing message names the route and nothing else; the validator's
 * own report goes on `cause`, where a developer and an error reporter can read
 * it but a rendered message cannot accidentally include it.
 */
export function invalidShapeError(path: string, detail: string): ApiError {
  const error = new ApiError(
    `The server's response for ${path} did not match the expected shape.`,
    0,
    CLIENT_ERROR_CODES.invalidShape,
  );
  error.cause = detail;
  return error;
}
