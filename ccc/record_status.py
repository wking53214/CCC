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

* ``erased`` or ``redacted`` if a human removed any matching record, or any
  record from this source with the same text under any candidate id (its
  fingerprint outlives the text). Removal wins over everything else: an erased
  claim must not come back into use through a second copy or a new id;
* ``rejected`` if a human rejected any record from this source with exactly
  this text, under any candidate id;
* ``superseded`` if any record from this source with exactly this text has a
  successor. The text is the old version; the successor is what counts now;
* ``held`` if a matching record is active and its stored text has exactly the
  fingerprint the caller presented. The fingerprint is recomputed from the
  stored text, not read from metadata, so what is compared is what CCC holds;
* ``altered`` if a matching record exists but none holds that exact text, so
  the item presented is not the item that was recorded;
* ``absent`` if nothing matches.

Who wrote the record
--------------------
Everything above trusts what the record says about itself: its actor and its
metadata can be written by anyone who can call ``ingest``, add to the store, or
edit a saved state file. So a consumer that needs to know the handoff itself
wrote the record passes ``attestation_key``. The handoff then stamps each record
with an HMAC over the source, the candidate id and the fingerprint of the stored
text (``attest``), and this module counts only records whose stamp verifies under
that key. A record without a valid stamp is never ``held``: if no matching record
is stamped the answer is ``unattested``, a refusal. The key is the caller's. CCC
holds no key of its own and never writes one anywhere. Without a key, nothing
changes, and the answer is exactly as unauthenticated as it was.

This is a read. It changes nothing: no record, no audit event, no rule
decision.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from .models import ActorType, ArtifactState, ProvenanceStatus, RelationshipType, content_digest

__all__ = [
    "ABSENT",
    "ALTERED",
    "ERASED",
    "HELD",
    "REDACTED",
    "REJECTED",
    "STATUSES",
    "SUPERSEDED",
    "UNATTESTED",
    "MachineRecords",
    "attest",
    "record_status",
]

HELD = "held"
ABSENT = "absent"
ALTERED = "altered"
ERASED = "erased"
REDACTED = "redacted"
UNATTESTED = "unattested"
REJECTED = "rejected"
SUPERSEDED = "superseded"

#: Every answer ``record_status`` can give.
STATUSES = (HELD, ABSENT, ALTERED, ERASED, REDACTED, UNATTESTED, REJECTED, SUPERSEDED)

#: Where the handoff's stamp lives in a record's metadata.
ATTESTATION_FIELD = "attestation"

_MIN_KEY_BYTES = 16


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_key(key: Any) -> bytes:
    if not isinstance(key, (bytes, bytearray)) or len(key) < _MIN_KEY_BYTES:
        raise ValueError(f"attestation_key must be at least {_MIN_KEY_BYTES} bytes")
    return bytes(key)


def attest(key: bytes, *, source: str, candidate_id: str, text_digest: str) -> str:
    """The stamp a handoff writes into a record's metadata, and ``record_status`` checks.

    HMAC-SHA256, untruncated, over the source, the candidate id and the fingerprint of the text the
    record stores. The key is the caller's; there is no default.
    """
    message = json.dumps(["ccc.handoff.v1", _require_text("source", source),
                          _require_text("candidate_id", candidate_id),
                          _require_text("text_digest", text_digest)], separators=(",", ":"))
    return hmac.new(_require_key(key), message.encode("utf-8"), hashlib.sha256).hexdigest()


def record_status(system: Any, *, source: str, candidate_id: str, text_digest: str,
                  attestation_key: bytes | None = None) -> str:
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
    if attestation_key is not None:
        _require_key(attestation_key)

    from_source = [
        artifact
        for artifact in system.store.artifacts.values()
        if artifact.origin.kind is ActorType.MODEL
        and artifact.origin.actor_id == source
        and (artifact.metadata or {}).get("source") == source
    ]
    matches = [a for a in from_source if (a.metadata or {}).get("candidate_id") == candidate_id]
    # The same text under any candidate id. An erased record keeps its fingerprint, so this finds it too.
    same_text = [a for a in from_source if a.content_digest == text_digest]
    removed = matches + same_text
    if any(a.state is ArtifactState.ERASED for a in removed):
        return ERASED
    if any(a.state is ArtifactState.REDACTED for a in removed):
        return REDACTED
    if any(a.provenance_status is ProvenanceStatus.REJECTED for a in same_text):
        return REJECTED
    if any(_superseded(system, a.artifact_id) for a in same_text):
        return SUPERSEDED
    if not matches:
        return ABSENT
    if attestation_key is not None:
        # Only a record the handoff stamped counts. The stamp is checked against the text the record stores now,
        # so a record whose text was edited after the stamp, or one that never had a stamp, is not counted.
        stamped = [a for a in matches if _stamped(a, attestation_key, source, candidate_id)]
        if not stamped:
            return UNATTESTED
        matches = stamped
    if any(a.available and content_digest(a.content) == text_digest for a in matches):
        return HELD
    return ALTERED


def _superseded(system: Any, artifact_id: str) -> bool:
    return any(event.target_id == artifact_id and event.source_id != artifact_id
               for event in system.lineage.related(artifact_id, RelationshipType.SUPERSEDES))


def _stamped(artifact: Any, key: bytes, source: str, candidate_id: str) -> bool:
    stamp = (artifact.metadata or {}).get(ATTESTATION_FIELD)
    stored = content_digest(artifact.content)
    if not isinstance(stamp, str) or stored is None:
        return False
    expected = attest(key, source=source, candidate_id=candidate_id, text_digest=stored)
    return hmac.compare_digest(stamp, expected)


class MachineRecords:
    """``record_status`` bound to one CCC system.

    This is the object a consumer is handed. Its one method, ``status``, is the
    record lookup CNS asks through (``cns_composition.ccc_admission``), so CNS
    can be given CCC's answer without being given CCC's store.
    """

    def __init__(self, system: Any, *, attestation_key: bytes | None = None) -> None:
        from .system import CCCSystem

        if not isinstance(system, CCCSystem):
            raise TypeError(f"MachineRecords needs a ccc.CCCSystem; got {type(system).__name__}")
        if attestation_key is not None:
            _require_key(attestation_key)
        self._system = system
        self._key = attestation_key

    def status(self, source: str, candidate_id: str, text_digest: str) -> str:
        return record_status(
            self._system, source=source, candidate_id=candidate_id, text_digest=text_digest,
            attestation_key=self._key,
        )
