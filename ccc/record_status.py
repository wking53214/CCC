"""Answer one question for a consumer: does CCC hold this machine output?

Why this exists
---------------
The governance design for the Triad says: the Triad thinks, CCC remembers and
guards, humans decide. Its second rule is "no CCC record, no use": when Triad
output is used inside the library, the point where it is used refuses it unless
CCC has recorded it. That refusal lives in CNS, at the integration point. This
module is CCC's side of it. CNS asks the question; only CCC reads its own
store to answer it. Nothing outside CCC needs to know how CCC keeps records,
and nothing outside CCC keeps a copy of them.

Like the rest of CCC it has no dependency, and it imports nothing from CNS.
It returns plain strings, which CNS compares against its own names.

What counts as recorded
-----------------------
A record matches when all of these hold:

* it was created by the machine actor named ``source`` (an ``Actor.model``
  with that id), so a record made by anyone else, carrying look-alike
  metadata, is not counted as that machine's output;
* its metadata names the same ``source`` and the same ``candidate_id``, which
  are the keys a machine handoff writes (``triad42.ccc_handoff`` does).

Then the answer is, in this order:

* ``erased`` or ``redacted`` if a human removed any matching record. Removal
  wins over everything else: an erased claim must not come back into use
  through a second copy;
* ``held`` if a matching record is active and its stored text has exactly the
  fingerprint the caller presented. The fingerprint is recomputed from the
  stored text, not read from metadata, so what is compared is what CCC holds;
* ``altered`` if a matching record exists but none holds that exact text, so
  the item presented is not the item that was recorded;
* ``absent`` if nothing matches.

This is a read. It changes nothing: no record, no audit event, no rule
decision.
"""

from __future__ import annotations

from typing import Any

from .models import ActorType, ArtifactState, content_digest

__all__ = [
    "ABSENT",
    "ALTERED",
    "ERASED",
    "HELD",
    "REDACTED",
    "STATUSES",
    "MachineRecords",
    "record_status",
]

HELD = "held"
ABSENT = "absent"
ALTERED = "altered"
ERASED = "erased"
REDACTED = "redacted"

#: Every answer ``record_status`` can give.
STATUSES = (HELD, ABSENT, ALTERED, ERASED, REDACTED)


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def record_status(system: Any, *, source: str, candidate_id: str, text_digest: str) -> str:
    """What CCC holds for one piece of machine output. See the module docstring.

    ``system`` is a ``ccc.CCCSystem``. Malformed arguments raise ``ValueError``
    rather than answer ``absent``: a question CCC cannot read is not a question
    it answered.
    """
    from .system import CCCSystem

    if not isinstance(system, CCCSystem):
        raise TypeError(f"record_status needs a ccc.CCCSystem; got {type(system).__name__}")
    _require_text("source", source)
    _require_text("candidate_id", candidate_id)
    _require_text("text_digest", text_digest)

    matches = [
        artifact
        for artifact in system.store.artifacts.values()
        if artifact.origin.kind is ActorType.MODEL
        and artifact.origin.actor_id == source
        and (artifact.metadata or {}).get("source") == source
        and (artifact.metadata or {}).get("candidate_id") == candidate_id
    ]
    if not matches:
        return ABSENT
    if any(a.state is ArtifactState.ERASED for a in matches):
        return ERASED
    if any(a.state is ArtifactState.REDACTED for a in matches):
        return REDACTED
    if any(a.available and content_digest(a.content) == text_digest for a in matches):
        return HELD
    return ALTERED


class MachineRecords:
    """``record_status`` bound to one CCC system.

    This is the object a consumer is handed. Its one method, ``status``, is the
    record lookup CNS asks through (``cns_composition.ccc_admission``), so CNS
    can be given CCC's answer without being given CCC's store.
    """

    def __init__(self, system: Any) -> None:
        from .system import CCCSystem

        if not isinstance(system, CCCSystem):
            raise TypeError(f"MachineRecords needs a ccc.CCCSystem; got {type(system).__name__}")
        self._system = system

    def status(self, source: str, candidate_id: str, text_digest: str) -> str:
        return record_status(
            self._system, source=source, candidate_id=candidate_id, text_digest=text_digest
        )
