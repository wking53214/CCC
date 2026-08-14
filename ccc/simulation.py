"""Constrained trajectory simulation with explicit input provenance."""

from __future__ import annotations

from .models import Actor, EpistemicStatus, ProvenanceStatus, SimulationRecord, new_id


class SimulationManager:
    def __init__(self, store, audit, rules) -> None:
        self.store = store
        self.audit = audit
        self.rules = rules

    def simulate(
        self,
        *,
        inputs: tuple[str, ...],
        assumptions: tuple[str, ...],
        shared_assumptions: tuple[str, ...],
        trajectory: tuple[str, ...],
        counterfactual: str,
        output: str,
        sensitivity: dict,
        limitations: tuple[str, ...],
        actor: Actor,
    ) -> SimulationRecord:
        input_provenance: list[tuple[str, str]] = []
        for artifact_id in inputs:
            artifact = self.store.require_artifact(artifact_id)
            input_provenance.append((artifact_id, artifact.provenance_status.value))
        self.rules.evaluate(
            "CCC-SIMULATION-001",
            bool(counterfactual.strip()) and bool(limitations),
            reason="simulation must preserve its assumptions and limitations",
            evidence=inputs,
        )
        simulation = SimulationRecord(
            simulation_id=new_id("simulation"),
            inputs=tuple(inputs),
            input_provenance=tuple(input_provenance),
            assumptions=tuple(assumptions),
            shared_assumptions=tuple(shared_assumptions),
            trajectory=tuple(trajectory),
            counterfactual=counterfactual,
            output=output,
            sensitivity=sensitivity,
            limitations=tuple(limitations),
            created_by=actor,
        )
        self.store.add_simulation(simulation)
        self.audit.record(
            actor=actor,
            operation="SIMULATE",
            object_id=simulation.simulation_id,
            previous_state=None,
            new_state={"epistemic_status": EpistemicStatus.SIMULATION.value, "shared_assumptions": list(shared_assumptions)},
            reason=counterfactual,
            provenance=ProvenanceStatus.ASSISTANT_PROPOSED,
            evidence=inputs,
            constitutional_rule="CCC-SIMULATION-001",
        )
        return simulation

    def promote_to_historical(self, simulation_id: str, *, actor: Actor, reason: str):
        self.rules.evaluate(
            "CCC-EPISTEMIC-002",
            False,
            reason="simulation output cannot become historical record",
        )
