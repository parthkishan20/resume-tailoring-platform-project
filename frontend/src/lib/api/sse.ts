/**
 * The server-sent-event readers: cancellable, and validating each frame.
 *
 * Three things are new here relative to the reader this replaces.
 *
 * **The stream is released when the consumer stops reading.** The old
 * generator held the `ReadableStreamDefaultReader` for the life of the
 * response and dropped it when a caller broke out of its `for await`, leaving
 * the body open until garbage collection happened to close it. A `finally`
 * cancels the reader on every exit: the last frame, a thrown error, an abort,
 * and the `return` that a `break` in the consumer's loop compiles into. This
 * is the browser half of the lifecycle fix task 2.1 made in the provider
 * adapter, which had no counterpart on this side.
 *
 * **Cancellation works.** `signal` was already a parameter and no caller ever
 * passed one (D-40), so closing a panel mid-generation left the request and
 * the server-side job running. The typed readers below take
 * {@link RequestOptions} like every other request-issuing function, so the
 * same `signal` a component already has for its queries cancels its stream.
 *
 * **Frames are validated.** Every call site used to cast: `event.data as {
 * delta: string }`. A frame that did not have that shape became `undefined`
 * appended to the transcript. The typed readers parse each payload with the
 * schema for its event name and throw a `RESPONSE_SHAPE_INVALID` `ApiError`
 * otherwise.
 *
 * {@link readSseStream} is the untyped reader, kept because the panels that
 * have not moved to the typed readers yet call it with the old signature. New
 * code uses {@link streamTailor}, {@link streamChat} or
 * {@link streamEvaluate}.
 */

import type { z } from "zod";

import { errorFromResponse, errorFromTransport, invalidShapeError } from "./errors";
import type { RequestOptions } from "./http";
import {
  chatDoneFrameSchema,
  evaluateDoneFrameSchema,
  generateDoneFrameSchema,
  sseErrorFrameSchema,
  sseProgressFrameSchema,
  sseTokenFrameSchema,
  type ChatDoneFrame,
  type ChatRequestBody,
  type EvaluateDoneFrame,
  type EvaluateRequestBody,
  type GenerateDoneFrame,
  type GenerateRequestBody,
  type SseErrorFrame,
  type SseProgressFrame,
  type SseTokenFrame,
} from "./schemas";

/** One frame, before its payload has been matched to a schema. */
export interface SseEvent {
  event: string;
  data: unknown;
}

/**
 * Read an SSE response frame by frame.
 *
 * `data` is `unknown`: this reader knows the transport, not the contract. Use
 * one of the typed readers below to get a validated payload.
 */
export async function* readSseStream(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (cause) {
    throw errorFromTransport(cause);
  }

  // A streaming route answers 200 before it starts work (D-55), so a status
  // here means the request never reached the generator at all: a 413, a 429,
  // or a 422 on the request body.
  if (!response.ok) throw await errorFromResponse(response);
  if (!response.body) throw invalidShapeError(path, "the response has no body");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          const raw = line.slice(5).trim();
          try {
            yield { event: currentEvent, data: JSON.parse(raw) };
          } catch {
            yield { event: currentEvent, data: raw };
          }
          currentEvent = "message";
        }
      }
    }
  } finally {
    // Reached on the last frame, on a throw, on an abort, and when the
    // consumer breaks out of its loop. Without this the body stayed open.
    void reader.cancel().catch(() => undefined);
  }
}

/** The schema each event name's payload must match, for one route. */
type FrameSchemas = Readonly<Record<string, z.ZodTypeAny>>;

async function* typedStream(
  path: string,
  body: unknown,
  schemas: FrameSchemas,
  options?: RequestOptions,
): AsyncGenerator<SseEvent> {
  for await (const frame of readSseStream(path, body, options?.signal)) {
    const schema = schemas[frame.event];
    if (schema === undefined) {
      throw invalidShapeError(path, `unexpected SSE event "${frame.event}"`);
    }
    const result = schema.safeParse(frame.data);
    if (!result.success) {
      throw invalidShapeError(path, `event: ${frame.event}: ${result.error.message}`);
    }
    yield { event: frame.event, data: result.data };
  }
}

/** A frame of `POST /api/resumes/stream`. */
export type TailorFrame =
  | { event: "progress"; data: SseProgressFrame }
  | { event: "done"; data: GenerateDoneFrame }
  | { event: "error"; data: SseErrorFrame };

/** A frame of `POST /api/chat/stream`. */
export type ChatFrame =
  | { event: "token"; data: SseTokenFrame }
  | { event: "done"; data: ChatDoneFrame }
  | { event: "error"; data: SseErrorFrame };

/** A frame of `POST /api/evaluate/stream`. */
export type EvaluateFrame =
  | { event: "progress"; data: SseProgressFrame }
  | { event: "done"; data: EvaluateDoneFrame }
  | { event: "error"; data: SseErrorFrame };

/**
 * Tailor the master resume to a job description, narrated as it happens.
 *
 * Ends on a `done` frame carrying the stored row, or an `error` frame carrying
 * the envelope. Read both: the HTTP status is 200 either way (D-55).
 */
export function streamTailor(
  body: GenerateRequestBody,
  options?: RequestOptions,
): AsyncGenerator<TailorFrame> {
  return typedStream(
    "/api/resumes/stream",
    body,
    {
      progress: sseProgressFrameSchema,
      done: generateDoneFrameSchema,
      error: sseErrorFrameSchema,
    },
    options,
  ) as AsyncGenerator<TailorFrame>;
}

/** One assistant turn, token by token. */
export function streamChat(
  body: ChatRequestBody,
  options?: RequestOptions,
): AsyncGenerator<ChatFrame> {
  return typedStream(
    "/api/chat/stream",
    body,
    {
      token: sseTokenFrameSchema,
      done: chatDoneFrameSchema,
      error: sseErrorFrameSchema,
    },
    options,
  ) as AsyncGenerator<ChatFrame>;
}

/** Score one resume against one job description. */
export function streamEvaluate(
  body: EvaluateRequestBody,
  options?: RequestOptions,
): AsyncGenerator<EvaluateFrame> {
  return typedStream(
    "/api/evaluate/stream",
    body,
    {
      progress: sseProgressFrameSchema,
      done: evaluateDoneFrameSchema,
      error: sseErrorFrameSchema,
    },
    options,
  ) as AsyncGenerator<EvaluateFrame>;
}
