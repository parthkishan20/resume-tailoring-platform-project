"""One repository module per resource.

Every function takes the database path as its first argument, blocks, and
returns a model from :mod:`resumetailor.db.models` -- never a ``sqlite3.Row``
and never a bare ``dict``. Callers dispatch them through ``asyncio.to_thread``.

The names are re-exported here so a caller needing two resources writes one
import. Import from the module itself when only one resource is involved.
"""

from __future__ import annotations

from resumetailor.db.repositories.chat import (
    add_chat_message,
    clear_chat,
    get_chat_messages,
)
from resumetailor.db.repositories.llm_requests import (
    get_llm_request_counts,
    record_llm_request,
)
from resumetailor.db.repositories.master_resume import (
    delete_master_resume,
    get_master_resume,
    upsert_master_resume,
)
from resumetailor.db.repositories.resumes import (
    create_resume,
    delete_resume,
    get_resume,
    list_resumes,
    update_resume,
)
from resumetailor.db.repositories.rules import get_rules, reset_rules, upsert_rules
from resumetailor.db.repositories.system_prompt import (
    get_system_prompt,
    reset_system_prompt,
    upsert_system_prompt,
)

__all__ = [
    "add_chat_message",
    "clear_chat",
    "create_resume",
    "delete_master_resume",
    "delete_resume",
    "get_chat_messages",
    "get_llm_request_counts",
    "get_master_resume",
    "get_resume",
    "get_rules",
    "get_system_prompt",
    "list_resumes",
    "record_llm_request",
    "reset_rules",
    "reset_system_prompt",
    "update_resume",
    "upsert_master_resume",
    "upsert_rules",
    "upsert_system_prompt",
]
