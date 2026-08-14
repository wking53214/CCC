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


class NotFound(CCCError):
    """A requested immutable object identifier is not present."""


class InvalidTransition(CCCError):
    """A state transition is not valid for the object's current state."""
