# backend/src/resumetailor/api/routers/chat.py
from __future__ import annotations
import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from resumetailor.api.schemas.errors import error_responses
from resumetailor.backend_api import BackendAPI
from resumetailor.core.config import get_settings
from resumetailor.db.models import ChatMessage
from resumetailor.db.repositories import get_chat_messages, add_chat_message, clear_chat, get_system_prompt
from resumetailor.deps import get_backend
from resumetailor.core.errors import BackendError
from resumetailor.core.security import MAX_CHAT_MESSAGE_CHARS
from resumetailor.domain.assistant import AssistantReply, run_assistant_turn

router = APIRouter()
logger = logging.getLogger(__name__)

# Cap what we send to the LLM; full history is still persisted and displayed.
LLM_HISTORY_LIMIT = 30


def _db_path() -> str:
    return get_settings().DB_PATH


def _pdfs_dir() -> str:
    return get_settings().PDFS_DIR


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _error_frame(exc: BackendError) -> str:
    """One SSE error frame, and the log line that keeps the detail.

    The last of D-53's three streaming routes, closed by task 2.2. This file
    was outside both task 2.4's ownership (which split `client_message` from
    `str(exc)`) and task 2.5's (which applied the split to the other two
    streams), so until now every `except` branch here put `str(exc)` straight
    into the frame: raw provider exception text, which for a LiteLLM error
    carries the request URL, the model routing and the provider name.
    `tests/test_security.py::test_chat_stream_still_leaks_provider_exception_text`
    was `xfail(strict=True)` for exactly that, and passes now.

    Both halves of the fix are here, as in the other two routes: an SSE error
    never reaches the handler in `core/errors.py`, so if this function did not
    log `exc.detail` the detail would be lost rather than made opaque. `code`
    is `exc.code` and not a literal, which is the other defect this file had
    the worst version of: all three branches below used to name a code by hand,
    so a `LLMEmptyResponseError` (D-59) reached the browser as
    `LLM_UNAVAILABLE`.
    """
    logger.error(
        "sse domain error: %s",
        exc.code,
        exc_info=exc,
        extra={"error_code": exc.code, "error_detail": exc.detail},
    )
    return _sse("error", {"error": exc.client_message, "code": exc.code})


class ChatRequest(BaseModel):
    message: str = Field(max_length=MAX_CHAT_MESSAGE_CHARS)


@router.get("/api/chat", response_model=list[ChatMessage])
async def get_history():
    return await asyncio.to_thread(get_chat_messages, _db_path())


@router.post(
    "/api/chat/stream",
    response_class=StreamingResponse,
    responses=error_responses(413, 422, 429),
)
async def chat_stream(body: ChatRequest, api: BackendAPI = Depends(get_backend)):
    async def event_gen():
        try:
            # Persist user message
            await asyncio.to_thread(add_chat_message, _db_path(), "user", body.message)

            # Build messages for LLM. The limit is applied by the query, not by
            # slicing a full-table fetch afterwards (D-21).
            history = await asyncio.to_thread(
                get_chat_messages, _db_path(), limit=LLM_HISTORY_LIMIT
            )
            sp_row = await asyncio.to_thread(get_system_prompt, _db_path())
            system_content = sp_row.content if sp_row else "You are ResumeTailor, an AI assistant."
            messages = [{"role": "system", "content": system_content}]
            messages += [{"role": m.role, "content": m.content} for m in history]

            # Stream the turn. The orchestration -- running whatever tools the
            # model asks for and feeding their results back -- is
            # `domain.assistant.run_assistant_turn` (D-33); this handler only
            # turns its events into frames, the same split task 2.5 drew
            # between `domain.tailoring.tailor` and this route's sibling.
            full_text = ""
            action: dict[str, object] | None = None
            async for event in run_assistant_turn(
                api, db_path=_db_path(), pdfs_dir=_pdfs_dir(), messages=messages
            ):
                if isinstance(event, AssistantReply):
                    full_text = event.text
                    action = (
                        {"type": event.action.type, "resume_id": event.action.resume_id}
                        if event.action is not None
                        else None
                    )
                else:
                    yield _sse("token", {"delta": event})

            # Persist assistant message. Tool-call and tool-result turns stay
            # out of the transcript on purpose: they are working state for one
            # request, not something `GET /api/chat` should ever show.
            await asyncio.to_thread(add_chat_message, _db_path(), "assistant", full_text)

            yield _sse("done", {"result": {"text": full_text, "action": action}})
        except BackendError as exc:
            yield _error_frame(exc)
        except Exception:
            # Not a domain error, so there is no vetted sentence to send: the
            # text of an unexpected exception is exactly what must not travel.
            logger.exception("sse chat failed", extra={"error_code": "CHAT_FAILED"})
            yield _sse("error", {"error": BackendError.client_message, "code": "CHAT_FAILED"})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.delete("/api/chat", status_code=204)
async def clear_history():
    await asyncio.to_thread(clear_chat, _db_path())
