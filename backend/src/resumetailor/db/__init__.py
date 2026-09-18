"""Database engine, migrations, models and repositories.

The layering is one-way: ``repositories`` depend on ``engine`` and ``models``,
``migrate`` and ``seed`` depend on ``engine``, and nothing here imports a
router, a service or an adapter.

Everything is keyed by ``user_id`` and every caller passes
:data:`DEFAULT_USER_ID`. The column exists because the schema was written with
more than one user in mind; the application has exactly one. See
``docs/ARCHITECTURE.md`` on the single-user assumption.
"""

from __future__ import annotations

DEFAULT_USER_ID = "default"

__all__ = ["DEFAULT_USER_ID"]
