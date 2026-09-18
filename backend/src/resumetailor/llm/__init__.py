"""The LLM provider boundary.

``port.py`` is the protocol, ``litellm_adapter.py`` is the real provider, and
``stub.py`` is the deterministic one the tests and ``LLM_MOCK`` run against.

Three modules support the real provider: ``config.py`` holds the limits of one
call, ``usage.py`` carries the token counts back out past a return type that
cannot hold them, and ``errors.py`` names the one failure
``core.errors`` does not.
"""
