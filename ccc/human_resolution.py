"""Neutral uncertainty representation and explicit human resolution events."""

from __future__ import annotations

from dataclasses import replace

from .models import Actor, ActorType, UncertaintyRecord, new_id


class HumanResolutionManager:
    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def ask(
        self,
        *,
        context: str,
        known: tuple[str, ...] = (),
        unknown: tuple[str, ...] = (),
        inferred: tuple[str, ...] = (),
        conflicted: tuple[str, ...] = (),
        candidates: tuple[str, ...] = (),
        question: str,
        actor: Actor,
    ) -> UncertaintyRecord:
        self.rules.evaluate(
            "CCC-UNCERTAINTY-001",
            bool(question.strip()),
            reason="uncertainty must be represented with a neutral question",
        )
        record = UncertaintyRecord(
            uncertainty_id=new_id("uncertainty"),
            context=context,
            known=tuple(known),
            unknown=tuple(unknown),
            inferred=tuple(inferred),
            conflicted=tuple(conflicted),
            candidates=tuple(candidates),
            requires_human_resolution=True,
            question=question,
            created_by=actor,
        )
        self.store.add_uncertainty(record)
        self.audit.record(
            actor=actor,
            operation="ASK_UNCERTAINTY",
            object_id=record.uncertainty_id,
            previous_state=None,
            new_state={"requires_human_resolution": True, "candidates": list(record.candidates)},
            reason="important cognitive fact is unresolved",
            constitutional_rule="CCC-UNCERTAINTY-001",
        )
        return record

    def resolve(self, uncertainty_id: str, *, choice: str, actor: Actor, reason: str, authorization_basis: str):
        record = self.store.uncertainties[uncertainty_id]
        self.rules.evaluate(
            "CCC-HUMAN-001",
            actor.kind is ActorType.HUMAN,
            reason="ambiguity resolution belongs to the human sovereign",
        )
        updated = replace(record, resolved_choice=choice, resolved_by=actor)
        self.store.replace_uncertainty(updated)
        self.audit.record(
            actor=actor,
            operation="RESOLVE_UNCERTAINTY",
            object_id=uncertainty_id,
            previous_state={"resolved_choice": record.resolved_choice},
            new_state={"resolved_choice": choice},
            reason=reason,
            constitutional_rule="CCC-HUMAN-001",
            authorization_basis=authorization_basis,
        )
        return updated

    def get(self, uncertainty_id: str) -> UncertaintyRecord:
        return self.store.uncertainties[uncertainty_id]
