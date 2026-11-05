"""The check an application can put in front of CCC's human-only operations.

CCC is independent: it imports nothing from CNS and names no identity system. A human operation is one only a human
may do: ``decide``, ``correct``, ``amend``, ``supersede``, ``redact``, ``erase``, ``accept``,
``establish_provenance``, ``reject``, ``ratify``, ``record_resolution``, ``resolve_uncertainty``, ``adopt_discovery``,
advancing a discovery to MANDATE, and an epistemic change to or from a human-held status (``classify``). Today CCC
checks that the actor is *labelled* human, and a label is all ``Actor.human("anyone")`` is. The application can hand
``CCCSystem`` a callable (``human_verifier``) that decides whether this human, for this act, is who they say.

WHAT THE VERIFIER SEES

A :class:`HumanRequest`: the operation, the actor's id, the ids the act is about (``target_ids``), the digest of any
new content it would write (``content_digest``, SHA-256 of the UTF-8 text, the same fingerprint CCC keeps on a
record), the ``authorization_basis``, and the ``attestation`` the caller passed. The attestation is an optional
keyword on every one of these operations. CCC does not read it, store it or judge it; it only carries it to the
verifier, which is where a signature or a token over the act can be checked. It is a keyword of the call, not part of
the call's identity, so passing it does not change the signature or the digest of the operation. The request is
frozen and holds deep copies, so a verifier cannot change what is about to be written.

WHAT COUNTS AS A NO

Anything other than the value ``True``: ``False``, ``None``, a truthy object, an exception from the verifier, a
request that cannot be built. A no raises :class:`ccc.errors.HumanVerificationRefused` before CCC touches its store,
its rules or its audit trail.

WHAT THIS DOES NOT DO

With no verifier configured nothing changes. The verifier is asked once per public call, never again beneath it
(``ratify`` calls ``accept``; one ask). It is never the machine ``write_permission``: a human operation does not ask
that, and the machine's roster does not ask this. The verifier is given to the constructor and is not saved with the
store, so a system reloaded from disk has none unless ``CCCSystem.load`` is given one again. The managers
(``system.provenance`` and the rest) are the layer beneath the facade and do not ask; a caller that goes round the
facade is not checked here.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from .models import content_digest

__all__ = ["HumanRequest", "HumanVerifier", "build_human_request"]


@dataclass(frozen=True)
class HumanRequest:
    """One human act a verifier is asked about."""

    operation: str
    actor_id: str
    target_ids: tuple[str, ...] = ()
    content_digest: str | None = None
    authorization_basis: str | None = None
    attestation: Any = None


#: A verifier: gets the request, permits only by returning exactly ``True``.
HumanVerifier = Callable[[HumanRequest], bool]


def build_human_request(
    operation: str,
    actor: Any,
    target_ids: tuple[str, ...],
    content: str | None,
    authorization_basis: str | None,
    attestation: Any,
) -> HumanRequest:
    """A request holding a copy of the attestation. Raises ``TypeError`` if the call cannot be described."""
    try:
        return HumanRequest(
            operation=operation,
            actor_id=actor.actor_id,
            target_ids=tuple(target_ids),
            content_digest=content_digest(content),
            authorization_basis=authorization_basis,
            attestation=copy.deepcopy(attestation),
        )
    except Exception as exc:
        raise TypeError(f"cannot describe the call to {operation}: {exc}") from exc
