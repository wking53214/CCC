"""Canonical terminology management with explicit provenance transitions."""

from __future__ import annotations

from dataclasses import replace

from .errors import ConstitutionViolation
from .models import Actor, ActorType, CanonicalTerm, ProvenanceStatus, TermStatus, new_id


class CanonicalizationManager:
    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def propose_term(
        self,
        *,
        term: str,
        definition: str,
        actor: Actor,
        source_material: tuple[str, ...] = (),
    ) -> CanonicalTerm:
        status = TermStatus.EXTERNAL if actor.kind is ActorType.EXTERNAL else TermStatus.PROPOSED
        provenance = ProvenanceStatus.USER_ESTABLISHED if actor.kind is ActorType.HUMAN else ProvenanceStatus.ASSISTANT_PROPOSED
        record = CanonicalTerm(
            term_id=new_id("term"),
            term=term,
            definition=definition,
            status=status,
            origin_actor=actor,
            provenance_status=provenance,
            source_material=tuple(source_material),
        )
        self.store.add_term(record)
        self.audit.record(
            actor=actor,
            operation="PROPOSE_TERM",
            object_id=record.term_id,
            previous_state=None,
            new_state={"status": status.value, "term": term},
            reason="terminology proposal recorded without canonical promotion",
            provenance=provenance,
            evidence=source_material,
            constitutional_rule="CCC-CANON-001",
        )
        return record

    def canonicalize(
        self,
        term_id: str,
        *,
        actor: Actor,
        source_material: tuple[str, ...],
        reason: str,
        authorization_basis: str,
    ) -> CanonicalTerm:
        self.rules.evaluate(
            "CCC-CANON-001",
            actor.kind is ActorType.HUMAN and bool(source_material) and bool(authorization_basis),
            reason="canonical status requires explicit human action and source material",
            evidence=source_material,
        )
        for source_id in source_material:
            source = self.store.require_artifact(source_id)
            if source.provenance_status not in {ProvenanceStatus.USER_ESTABLISHED, ProvenanceStatus.USER_ACCEPTED}:
                raise ConstitutionViolation("CCC-CANON-001", "unknown-origin source cannot establish canonical terminology")
        term = self.store.terms[term_id]
        updated = replace(term, status=TermStatus.CANONICAL, provenance_status=ProvenanceStatus.USER_ESTABLISHED, source_material=tuple(source_material), canonicalized_by=actor)
        self.store.replace_term(updated)
        self.audit.record(
            actor=actor,
            operation="CANONICALIZE_TERM",
            object_id=term_id,
            previous_state={"status": term.status.value, "definition": term.definition},
            new_state={"status": updated.status.value, "definition": updated.definition},
            reason=reason,
            provenance=updated.provenance_status,
            evidence=source_material,
            constitutional_rule="CCC-CANON-001",
            authorization_basis=authorization_basis,
        )
        return updated

    def deprecate(self, term_id: str, *, actor: Actor, reason: str, authorization_basis: str) -> CanonicalTerm:
        self.rules.evaluate("CCC-HUMAN-001", actor.kind is ActorType.HUMAN and bool(authorization_basis), reason="term lifecycle change is explicit")
        term = self.store.terms[term_id]
        updated = replace(term, status=TermStatus.DEPRECATED)
        self.store.replace_term(updated)
        self.audit.record(
            actor=actor,
            operation="DEPRECATE_TERM",
            object_id=term_id,
            previous_state={"status": term.status.value},
            new_state={"status": updated.status.value},
            reason=reason,
            provenance=term.provenance_status,
            constitutional_rule="CCC-HUMAN-001",
            authorization_basis=authorization_basis,
        )
        return updated

    def supersede(
        self,
        term_id: str,
        *,
        definition: str,
        actor: Actor,
        source_material: tuple[str, ...],
        reason: str,
        authorization_basis: str,
    ) -> CanonicalTerm:
        old = self.canonicalize(term_id, actor=actor, source_material=source_material, reason=reason, authorization_basis=authorization_basis)
        replacement = self.propose_term(term=old.term, definition=definition, actor=actor, source_material=source_material)
        canonical = self.canonicalize(replacement.term_id, actor=actor, source_material=source_material, reason=reason, authorization_basis=authorization_basis)
        self.store.replace_term(replace(old, status=TermStatus.SUPERSEDED, superseded_by=canonical.term_id))
        self.audit.record(
            actor=actor,
            operation="SUPERSEDE_TERM",
            object_id=old.term_id,
            previous_state={"status": old.status.value},
            new_state={"status": TermStatus.SUPERSEDED.value, "superseded_by": canonical.term_id},
            reason=reason,
            provenance=old.provenance_status,
            evidence=source_material,
            constitutional_rule="CCC-CANON-001",
            authorization_basis=authorization_basis,
        )
        return canonical
