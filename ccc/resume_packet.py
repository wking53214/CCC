"""Session resume packet, built on demand from CCC's own open items.

Read-only. Nothing is stored and nothing is written to the audit trail. The
packet is a snapshot of what is still unresolved in a CCCSystem at the moment
it is built.

What CCC can supply:
- active_pins: uncertainty records still waiting for a human choice, and
  conflict records not yet resolved.
- active_concepts: the road sign categories linked to those open pins.

What CCC does not store, so the caller must supply: id, title,
current_problem and next_action.

The output uses the same packet type and version as Synapsis's resume packet
(synapsis/memory/resume_packet.py), so a packet built here can be read by
Synapsis's import_packet.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .models import ConflictStatus

RESUME_PACKET_TYPE = "synapsis_resume_packet"
RESUME_PACKET_VERSION = "1.0"

_TEXT_FIELDS = ("packet_id", "title", "current_problem", "next_action")


def open_pins(system: Any) -> list[str]:
    """Ids of open uncertainty and unresolved conflict records, in store order."""
    store = system.store
    pins = [
        record.uncertainty_id
        for record in store.uncertainties.values()
        if record.requires_human_resolution and record.resolved_choice is None
    ]
    pins.extend(
        record.conflict_id
        for record in store.conflicts.values()
        if record.status is not ConflictStatus.RESOLVED
    )
    return pins


def active_concepts(system: Any, pins: list[str]) -> list[str]:
    """Road sign categories linked to any open pin, deduplicated in store order."""
    pin_set = set(pins)
    concepts: list[str] = []
    for sign in system.store.road_signs.values():
        if not pin_set.intersection(sign.linked_ids):
            continue
        value = sign.category.value
        if value not in concepts:
            concepts.append(value)
    return concepts


def build_resume_packet(
    system: Any,
    *,
    packet_id: str,
    title: str,
    current_problem: str,
    next_action: str,
    created: datetime | None = None,
) -> dict[str, Any]:
    """Build a resume packet dict from the system's open items. Read-only."""
    values = {
        "packet_id": packet_id,
        "title": title,
        "current_problem": current_problem,
        "next_action": next_action,
    }
    for name in _TEXT_FIELDS:
        if not isinstance(values[name], str):
            raise TypeError(f"resume packet field {name!r} must be a string")

    pins = open_pins(system)
    when = created if created is not None else datetime.now(UTC)
    return {
        "packet_type": RESUME_PACKET_TYPE,
        "version": RESUME_PACKET_VERSION,
        "state": {
            "id": packet_id,
            "title": title,
            "current_problem": current_problem,
            "next_action": next_action,
            "active_concepts": active_concepts(system, pins),
            "active_pins": pins,
            "created": when.isoformat(),
        },
    }
