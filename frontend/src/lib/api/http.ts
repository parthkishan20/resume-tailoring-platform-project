/**
 * One request function: cancellable, and validating on the way back.
 *
 * Two defects meet here.
 *
 * **D-40.** No `AbortController` existed anywhere in the codebase. Every
 * function in `client.ts` takes a {@link RequestOptions} with an optional
 * `signal`, and passes it to `fetch`, so a caller can cancel: an effect
 * cleanup, a closing drawer, a navigation, or TanStack Query, which hands its
 * `queryFn` a signal and aborts it on unmount and on every refetch. A
 * cancellation is not an error and is rethrown as the `AbortError` it is,
 * never wrapped, so the callers that check for it keep working.
 *
 * **D-60.** Nothing validated a response. `parseJson` runs every body through
 * a zod schema, so a shape the client did not expect fails here, at the
 * boundary, with the route in the message, rather than three components later
 * as an undefined property.
 *
 * {@link abortable} is the other half of "takes or creates": code with no
 * signal of its own gets one and the handle to cancel it in a single call.
 */

import type { z } from "zod";

import { errorFromResponse, errorFromTransport, invalidShapeError } from "./errors";

/** What every request-issuing function accepts. */
export interface RequestOptions {
  /**
   * Cancels the request when aborted. TanStack Query supplies one to every
   * `queryFn` and `mutationFn`; outside it, use {@link abortable}.
   */
  signal?: AbortSignal;
}

/**
 * A fresh signal and the function that cancels it.
 *
 * For imperative call sites that have no signal to pass on: hold `cancel` and
 * call it from a cleanup, an unmount, or a "stop" button.
 *
 * ```ts
 * const { signal, cancel } = abortable();
 * void api.listResumes("date", "desc", 1, { signal });
 * return cancel; // useEffect cleanup
 * ```
 */
export function abortable(): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController();
  return { signal: controller.signal, cancel: () => controller.abort() };
}

const JSON_HEADERS: Readonly<Record<string, string>> = {
  "Content-Type": "application/json",
};

async function send(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init);
  } catch (cause) {
    throw errorFromTransport(cause);
  }
}

function parse<T>(path: string, schema: z.ZodType<T>, text: string): T {
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    throw invalidShapeError(path, "the body is not JSON");
  }
  const result = schema.safeParse(body);
  if (!result.success) {
    throw invalidShapeError(path, result.error.message);
  }
  return result.data;
}

/**
 * `GET`/`PUT`/`POST`/`PATCH`/`DELETE` returning a body, validated.
 *
 * Throws an `ApiError` for any non-2xx status, for a transport failure, and
 * for a 2xx whose body does not match `schema`. Rethrows an `AbortError`
 * untouched.
 */
export async function requestJson<T>(
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {},
): Promise<T> {
  const response = await send(path, init);
  if (!response.ok) throw await errorFromResponse(response);
  return parse(path, schema, await response.text());
}

/**
 * A request whose success has no body: the three 204 routes.
 *
 * D-31's fix lives here now. The original client called `res.json()`
 * unconditionally, which rejects on an empty body, so every successful DELETE
 * looked like a failure. Nothing is read at all rather than reading and
 * discarding, because a 204 is not permitted to have a body to read.
 */
export async function requestNoContent(path: string, init: RequestInit = {}): Promise<void> {
  const response = await send(path, init);
  if (!response.ok) throw await errorFromResponse(response);
}

/** A JSON request body, with the header that goes with it. */
export function jsonBody(body: unknown, method: string, options?: RequestOptions): RequestInit {
  return {
    method,
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
    signal: options?.signal,
  };
}

/** A request with a method and no body. */
export function bare(method: string, options?: RequestOptions): RequestInit {
  return { method, signal: options?.signal };
}

/**
 * A query string from only the parameters that were given.
 *
 * `URLSearchParams` rather than a template literal: every value here is
 * user-influenced, and a page number arriving as something other than a number
 * should be encoded, not interpolated.
 */
export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded === "" ? "" : `?${encoded}`;
}
