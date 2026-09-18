"""The LLM provider boundary.

``port.py`` is the protocol, ``litellm_adapter.py`` is the real provider, and
``stub.py`` is the deterministic one the tests and ``LLM_MOCK`` run against.
"""
