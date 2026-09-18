# backend/src/resumetailor/api/routers/chat.py
from __future__ import annotations
import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from resumetailor.backend_api import BackendAPI
from resumetailor.core.config import get_settings
from resumetailor.database import get_chat_messages, add_chat_message, clear_chat, get_system_prompt
from resumetailor.deps import get_backend
from resumetailor.core.errors import LLMAuthError, LLMUnavailableError

router = APIRouter()

# Cap what we send to the LLM; full history is still persisted and displayed.
LLM_HISTORY_LIMIT = 30


def _db_path() -> str:
    return get_settings().DB_PATH


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class ChatRequest(BaseModel):
    message: str


@router.get("/api/chat")
async def get_history():
    return await asyncio.to_thread(get_chat_messages, _db_path())


@router.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, api: BackendAPI = Depends(get_backend)):
    async def event_gen():
        try:
            # Persist user message
            await asyncio.to_thread(add_chat_message, _db_path(), "user", body.message)

            # Build messages for LLM
            history = await asyncio.to_thread(get_chat_messages, _db_path())
            sp_row = await asyncio.to_thread(get_system_prompt, _db_path())
            system_content = sp_row["content"] if sp_row else "You are ResumeTailor, an AI assistant."
            messages = [{"role": "system", "content": system_content}]
            messages += [
                {"role": m["role"], "content": m["content"]}
                for m in history[-LLM_HISTORY_LIMIT:]
            ]

            # Stream response
            full_text = ""
            async for delta in await api.stream(messages):
                full_text += delta
                yield _sse("token", {"delta": delta})

            # Persist assistant message
            await asyncio.to_thread(add_chat_message, _db_path(), "assistant", full_text)

            yield _sse("done", {"result": {"text": full_text, "action": None}})
        except LLMAuthError as exc:
            yield _sse("error", {"error": str(exc), "code": "LLM_AUTH_ERROR"})
        except LLMUnavailableError as exc:
            yield _sse("error", {"error": str(exc), "code": "LLM_UNAVAILABLE"})
        except Exception as exc:
            yield _sse("error", {"error": str(exc), "code": "CHAT_FAILED"})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.delete("/api/chat", status_code=204)
async def clear_history():
    await asyncio.to_thread(clear_chat, _db_path())
