"""Typed failures raised by the CCC enforcement layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CCCError(Exception):
    """Base class for expected CCC failures."""


@dataclass
class ConstitutionViolation(CCCError):
    """A constitutional rule rejected an operation."""

    rule_id: str
    reason: str
    decision: str = "REJECT"
    evidence: tuple[str, ...] = field(default_factory=tuple)
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.rule_id}: {self.reason}"


class WritePermissionRefused(CCCError):
    """The permission check the application gave CCC did not say yes, so the call did nothing.

    Raised before CCC touches its store, its rules or its audit trail. Only the exact value ``True`` permits;
    an error from the check is a refusal too, and the error is the ``__cause__``."""

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(f"{operation}: {reason}")
        self.operation = operation
        self.reason = reason


class HumanVerificationRefused(CCCError):
    """The verifier the application gave CCC did not say yes, so the human operation did nothing.

    Raised before CCC touches its store, its rules or its audit trail. Only the exact value ``True`` permits;
    an error from the verifier is a refusal too, and the error is the ``__cause__``."""

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(f"{operation}: {reason}")
        self.operation = operation
        self.reason = reason


class NotFound(CCCError):
    """A requested immutable object identifier is not present."""


class DuplicateId(CCCError):
    """An object with this identifier already exists, so it was not replaced."""


class InvalidTransition(CCCError):
    """A state transition is not valid for the object's current state."""


class PrivateSourcesNotStated(CCCError):
    """A machine finding was recorded before the caller stated which sources
    are private. CCC names no repositories itself; the application that
    wires it in states the list (an empty one included), so the private-source
    guard cannot be lost by forgetting it."""
