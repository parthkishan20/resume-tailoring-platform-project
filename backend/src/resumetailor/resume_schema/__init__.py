"""The single source of truth for the resume contract.

``models.py`` derives the contract from RenderCV's own Pydantic models;
``prompt.py`` generates the LLM-facing schema text from those models;
``sections.py`` and ``normalize.py`` repair a document into that shape and
report what they had to remove; ``repair.py`` is the schema backstop;
``validate.py`` checks a document without rendering it.

Importing this package imports RenderCV. That is deliberate: a RenderCV whose
schema modules have moved fails the process at startup instead of silently
disabling validation at request time. See ``models.py`` and PLAN.md D-17.
"""
