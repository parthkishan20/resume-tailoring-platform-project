"""Located render problems, as data rather than as terminal output.

``RenderError`` carries the raw stdout and stderr of a CLI written for a human
terminal — Rich box drawing, ANSI, the lot — and that string reaches the
browser verbatim. Rewriting what the client sees is task 2.4's (D-53), so
nothing here changes any existing message.

What this module adds is the shape the editor eventually needs: a validation
failure that RenderCV reports *structurally* becomes a list of
:class:`RenderIssue`, each pointing at the field that caused it. That is what
``resume_schema.validate`` returns, and what the repair backstop prunes on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rendercv.exception import RenderCVUserValidationError


@dataclass(frozen=True)
class RenderIssue:
    """One problem RenderCV found, and where in the document it is.

    Attributes:
        location: The schema path, e.g. ``("cv", "sections", "experience", "0")``.
            Empty when RenderCV could not attribute the problem to a field,
            which is what happens for a YAML syntax error.
        message: RenderCV's own explanation, unmodified.
        input: The offending value as RenderCV rendered it.
    """

    location: tuple[str, ...] = ()
    message: str = ""
    input: str = ""

    @property
    def path(self) -> str:
        """The location as a dotted path, or ``"<document>"`` when unlocated."""
        return ".".join(self.location) if self.location else "<document>"


@dataclass(frozen=True)
class ValidationOutcome:
    """The result of validating one document against RenderCV's schema."""

    issues: list[RenderIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def issues_from_validation_error(
    exc: RenderCVUserValidationError,
) -> list[RenderIssue]:
    """Convert RenderCV's structured validation errors into issues.

    ``schema_location`` is ``None`` for a YAML parse failure — the error is
    about the file, not a field — so those issues carry an empty location
    rather than being dropped.
    """
    return [
        RenderIssue(
            location=tuple(error.schema_location)
            if error.schema_location is not None
            else (),
            message=error.message,
            input=str(error.input),
        )
        for error in exc.validation_errors
    ]
