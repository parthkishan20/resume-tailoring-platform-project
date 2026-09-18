/**
 * Where `readSseStream` used to live.
 *
 * The reader itself is now `lib/api/sse.ts`, alongside the typed per-route
 * readers that validate each frame. This module stays because five panels
 * under `src/components/**` and `src/features/**` import `@/lib/sse`, and none
 * of those files belongs to task 2.2. New code uses `streamTailor`,
 * `streamChat` or `streamEvaluate` from `@/lib/api`, which give a validated,
 * discriminated frame instead of `data: unknown` and a cast.
 */

export { readSseStream, type SseEvent } from "@/lib/api";
