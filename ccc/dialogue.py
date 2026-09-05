"""The confirm/refine/42 dialogue loop.

CCC already had the primitive this needed: human_resolution.ask()/resolve()
records a set of candidates and a human-attributed choice, gated by
CCC-HUMAN-001 so only a real human can resolve one. That existed, unused,
the whole time the rest of this project kept saying "the dialogue engine
doesn't exist as software." It was half right -- the primitive existed, the
protocol around it didn't: iterate, let "other" branch to new candidates
instead of forcing a pick from a fixed list, and terminate at either a
confirmed choice or an explicit 42 (the record doesn't establish this -- a
complete, honest answer, not a failure, same spirit as Triad-42's "no 42
identified" and CCC's own PROVENANCE_UNCERTAIN).

This is deliberately a thin wrapper, not a reimplementation: every round
still goes through the real ask()/resolve() calls, so the audit trail,
CCC-HUMAN-001 gating, and UncertaintyRecord storage are all the real thing,
not simulated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from .human_resolution import HumanResolutionManager
from .models import Actor, ActorType

UNKNOWN_SENTINEL = "42"


@dataclass(frozen=True)
class DialogueOutcome:
    terminal: str  # "CONFIRMED" or "UNKNOWN"
    choice: Optional[str]
    rounds: int
    uncertainty_ids: Tuple[str, ...]


class DialogueEngine:
    """Wraps HumanResolutionManager with the loop William specified: present
    candidates, accept a pick / "other" (branch) / 42 (honest unknown),
    repeat until terminal."""

    def __init__(self, human_resolution: HumanResolutionManager, *, max_rounds: int = 10):
        self.human_resolution = human_resolution
        self.max_rounds = max_rounds

    def run(
        self,
        *,
        context: str,
        question: str,
        candidates: Tuple[str, ...],
        respond: Callable[[Tuple[str, ...]], str],
        branch: Callable[[Tuple[str, ...]], Tuple[str, ...]],
        actor: Actor,
        human_actor: Actor,
        known: Tuple[str, ...] = (),
        unknown: Tuple[str, ...] = (),
        inferred: Tuple[str, ...] = (),
        conflicted: Tuple[str, ...] = (),
    ) -> DialogueOutcome:
        """
        `respond(current_candidates)` returns one of: a string exactly
        matching one of `current_candidates` (confirms it), the literal
        string "other" (reject all of these, branch to new candidates), or
        UNKNOWN_SENTINEL / "42" (the record doesn't establish this --
        terminate honestly). `branch(prior_candidates)` is only called
        after "other" and must return a new, non-empty candidate tuple.

        `actor` proposes the round (may be machine-origin); `human_actor`
        must be an actual human -- CCC-HUMAN-001, enforced by
        human_resolution.resolve() itself, not re-implemented here.
        """
        if human_actor.kind is not ActorType.HUMAN:
            raise ValueError(
                "resolution can only be attributed to a real human actor -- "
                "the dialogue proposes, it does not get to resolve itself"
            )
        if not candidates:
            raise ValueError("a dialogue needs at least one starting candidate")

        uncertainty_ids = []
        current = candidates
        for round_number in range(1, self.max_rounds + 1):
            record = self.human_resolution.ask(
                context=context, question=question, candidates=current,
                known=known, unknown=unknown, inferred=inferred, conflicted=conflicted,
                actor=actor,
            )
            uncertainty_ids.append(record.uncertainty_id)
            response = respond(current)

            if response == UNKNOWN_SENTINEL:
                self.human_resolution.resolve(
                    record.uncertainty_id, choice=UNKNOWN_SENTINEL, actor=human_actor,
                    reason="the record does not establish this",
                    authorization_basis="explicit human 42",
                )
                return DialogueOutcome("UNKNOWN", None, round_number, tuple(uncertainty_ids))

            if response == "other":
                new_candidates = branch(current)
                if not new_candidates:
                    raise ValueError("branch() must return at least one new candidate")
                current = new_candidates
                continue

            if response not in current:
                raise ValueError(
                    f"response {response!r} is not one of the presented candidates, "
                    '"other", or the 42 sentinel -- refusing an out-of-protocol answer'
                )
            self.human_resolution.resolve(
                record.uncertainty_id, choice=response, actor=human_actor,
                reason="human confirmed this candidate",
                authorization_basis="explicit human confirmation",
            )
            return DialogueOutcome("CONFIRMED", response, round_number, tuple(uncertainty_ids))

        raise RuntimeError(f"dialogue did not terminate within {self.max_rounds} rounds")
