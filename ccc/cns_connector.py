"""Optional connector to CNS (``cns.gate``).

CCC is independent. It has no runtime dependency, imports nothing from CNS
when it loads, and its whole suite passes with CNS absent. This module is the
one place that knows CNS exists, and it asks for CNS only when one of its
CNS-facing functions is called. Without CNS installed, :func:`judge`,
:class:`CccGate`, :func:`cns_chain`, :func:`attempt_digest` and
:func:`to_cns_result` raise :class:`CnsNotInstalled`, which carries the install
command. :func:`attempt`, :class:`Attempt` (including ``Attempt.run``),
:func:`cns_available` and :data:`TRANSITIONS` need no CNS and work either way.
Nothing else in CCC is affected.

What CCC judges
---------------
CCC judges an *attempted transition* before it happens. The transitions this
module judges evaluate their constitutional rules before they change any
record, so a refusal means the transition never starts. That is the ALPHA end
of the CNS gate contract. CCC has no outcome end: it does not judge a produced
result on its way out. ``CCCSystem.validate_constitution()`` is a
read-only invariant report over the whole store and gates nothing, so this
connector does not present it as an OMEGA gate. ``cns_chain(...).complete()``
is therefore ``False`` by design, which is CNS's own finding about a repo
that carries one end only, stated honestly rather than padded.

CCC's native verdict is not a value that is returned. An admitted transition
returns the updated record; a refused one raises. The refusals are
:class:`~ccc.errors.ConstitutionViolation` (a rule said no),
:class:`~ccc.errors.InvalidTransition` (the state machine has no such edge)
and :class:`~ccc.errors.NotFound`, plus the ``ValueError`` and ``KeyError``
CCC raises for malformed input and unknown ids. This module translates that
outcome, for one attempted call, into a bound ``cns.gate.GateResult``.

The mapping, and why
--------------------
=====================  ==============================================
CCC                    CNS
=====================  ==============================================
where it judges        ``ALPHA``. Rules run before any mutation.
the call returns       ``PASS``
ConstitutionViolation  ``RETRY`` when a human could repair it (below)
                       ``TERMINAL_BREACH`` when no human input could
InvalidTransition      ``TERMINAL_BREACH``: the state machine has no
                       such edge, nothing repairs this attempt
NotFound               ``TERMINAL_BREACH``: there is nothing to judge
ValueError, KeyError   ``TERMINAL_BREACH``: CCC refused the input
any other exception    not translated; it propagates (never a PASS)
reason                 the refusal's own text. For a rule it is
                       ``"<rule_id>: <reason>"`` exactly as CCC raises it
judged content         ``subject`` (a label, default the operation
                       name) and ``subject_digest``, which is
                       ``cns.gate.subject_digest`` over the attempted
                       call: ``{"operation", "arguments"}``
=====================  ==============================================

Retry versus breach. In the CNS contract a retry is a verdict that a changed
re-attempt can overcome, and a terminal breach is an abort that no change
repairs. For a constitutional refusal the connector does not guess which it is
from the rule's name or from the prose of its registry entry. It finds out.
After a refusal it takes a second scratch copy of the store and runs the *same*
operation by the *same* actor on the *same* target again, with only the human
inputs CCC's rules ask for added:

* a non-empty ``authorization_basis``;
* ``human_event=True`` where the operation takes one;
* a human-established record, created on the scratch copy, to stand as the
  evidence root: appended to ``evidence_ids``, given as ``source_material``,
  and, for ``classify``, attached to the artifact as support.

If CCC admits that call, the verdict is ``RETRY``: a human who supplies those
inputs gets this call admitted. If it does not, the verdict is
``TERMINAL_BREACH``. The probe never changes the actor, the operation or the
target, so:

* a model, system or external actor attempting a human-only operation is
  ``TERMINAL_BREACH``, whatever else the call says. That is what CCC itself
  calls *blocked* (``self_promotion_blocked`` in the demonstration). The human
  who could do it is a different actor making a different call, and gets a
  verdict of their own;
* a refusal that no human input reaches is ``TERMINAL_BREACH``: erased
  material (CCC has no restore), machine consensus promoted to human-established
  fact, a simulation promoted to history, a claim attached to itself, an unknown
  id, a missing state edge. So is a call that CCC cannot run even with those
  inputs added (an argument of the wrong type): no repair was shown;
* a human who left out the authorization basis, the human event or the
  evidence root, on a call that is otherwise admissible, gets ``RETRY``: for every
  rule alike, not by which rule happened to fire. (Unknown ids are never repaired
  by the probe, so the same omission on a target that does not exist is
  ``TERMINAL_BREACH``.)

The stand-in root is on the scratch copy only. ``RETRY`` says a human-established
record in that role would be enough; a real human has to have or make one.

What is bound, and what is not
------------------------------
The digest covers the attempted call: the operation and every argument,
after binding to the real signature and applying defaults, so positional and
keyword spellings of one call digest alike. It does not cover the store's
state when the call was judged; the same call can be refused today and
admitted after an evidence root is attached.

Arguments must be expressible as ``str``, ``int``, ``float``, ``bool``,
``None``, sequences and mappings of those, plus CCC's own ``Actor`` and enums,
and the :class:`Attempt` is built only if the digest of that rendering can be
computed. Everything else raises ``TypeError`` when the attempt is built, so a
verdict is never bound to a lossy rendering or to nothing, and nothing that is
accepted fails later. That includes: NaN and infinities; sets, bytes, datetimes
and other types; mapping keys that collide once stringified; text with a lone
surrogate (it cannot be encoded for the digest); integers wider than
:data:`MAX_INT_BITS` bits; and nesting (or a cycle) deeper than
:data:`MAX_DEPTH` containers. CCC itself accepts some of these natively.

An :class:`Attempt` keeps its own copy of the arguments. If a nested value is
changed after the attempt was built, ``Attempt.run`` and :func:`judge` raise
:class:`AttemptChanged` instead of running something that was not digested.

Preflight
---------
CCC fuses its check with its mutation, so the only faithful predicate is the
real operation. :func:`judge` and :class:`CccGate` therefore run the attempt
on a scratch copy of the store (CCC's own JSON snapshot round trip) and
translate what happened there. The live system is never touched. The cost is
one snapshot of the store per check, O(store): measured, a 5000-artifact store
takes about 1.5 to 2 seconds where the real operation takes about 0.2
milliseconds (a refusal loads the snapshot once more, a few tenths of a second
at that size). The snapshot is a JSON file of the whole store, live content
included, written to a private temporary directory (mode 0700) and removed
when the check ends. A store CCC cannot snapshot (JSON cannot render something
in its metadata, nesting too deep) cannot be preflighted: :func:`judge` raises
:class:`PreflightError` rather than guess. That error is neither a
``ValueError`` nor a ``TypeError``, so it cannot be mistaken for a refusal. The
real operation still enforces the same rules inline when the caller performs it;
nothing here replaces that.

What is judged
--------------
:data:`TRANSITIONS` is the set of ``CCCSystem`` operations that move material
toward human authority, promote an epistemic status, rewrite history, or
resolve something that belongs to a human, each of which evaluates its rules
before it changes a record. Not judged, on purpose:

* ``derive`` (and its aliases ``infer``, ``interpret``): it ingests a proposal
  first and attaches evidence second, so a refusal at the attach step follows an
  ingest. It is not a judgement that happens entirely before the work starts.
* ``record`` and the other aliases of judged operations.
* ``resolve``, a dispatcher over ``resolve_uncertainty`` and
  ``record_resolution``, which are judged directly.
* Operations that only record something new and validate its shape
  (``detect_conflict``, ``ask`` and road signs). They move nothing toward
  human authority.

An operation outside :data:`TRANSITIONS` raises ``ValueError`` when an
:class:`Attempt` is built; the connector never judges what it does not cover.

Install with the extra, from a checkout of CCC: ``pip install -e '.[cns]'``.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import math
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Callable, Iterator, Mapping

from .conflict import ConflictManager
from .discovery import DiscoveryManager
from .errors import CCCError, ConstitutionViolation
from .human_resolution import HumanResolutionManager
from .models import Actor, EpistemicStatus
from .store import CCCStore
from .system import CCCSystem

__all__ = [
    "Attempt",
    "AttemptChanged",
    "CccGate",
    "CnsNotInstalled",
    "GATE_NAME",
    "MAX_DEPTH",
    "MAX_INT_BITS",
    "PreflightError",
    "TRANSITIONS",
    "attempt",
    "attempt_digest",
    "cns_available",
    "cns_chain",
    "judge",
    "to_cns_result",
]

INSTALL_HINT = "pip install -e '.[cns]' (run from a checkout of ccc)"

#: The name every verdict from this connector carries as ``GateResult.gate``.
#: The rule that refused, if one did, is at the front of ``reason``.
GATE_NAME = "ccc.transition"

#: What ``reason`` says when nothing refused the attempt.
PASS_REASON = "admitted: no constitutional rule refused this transition"

#: The most containers an argument may nest. Deeper (or cyclic) arguments raise
#: ``TypeError`` when the attempt is built: they would overflow the stack in the
#: digest, and CCC cannot be asked to judge what the connector cannot bind.
MAX_DEPTH = 64

#: The widest integer an argument may be, in bits. Wider ones raise ``TypeError``
#: when the attempt is built: ``str(int)`` is refused for very long integers
#: (``sys.set_int_max_str_digits``), and the digest renders integers as text.
#: 2048 bits is 617 digits, below the interpreter's smallest allowed limit.
MAX_INT_BITS = 2048

#: The ``CCCSystem`` operations the connector judges (see the module docstring).
TRANSITIONS: tuple[str, ...] = (
    "ingest",
    "attach_evidence",
    "establish_provenance",
    "accept",
    "reject",
    "ratify",
    "classify",
    "decide",
    "correct",
    "amend",
    "supersede",
    "redact",
    "erase",
    "discover",
    "adopt_discovery",
    "advance_discovery",
    "record_resolution",
    "resolve_uncertainty",
)

#: Facade methods that forward ``*args, **kwargs`` and so say nothing about their
#: arguments. Their arguments are bound against the method they forward to, which
#: is where CCC gives them names.
_FORWARDED = {
    "discover": DiscoveryManager.discover,
    "adopt_discovery": DiscoveryManager.adopt,
    "advance_discovery": DiscoveryManager.advance,
    "record_resolution": ConflictManager.record_resolution,
    "resolve_uncertainty": HumanResolutionManager.resolve,
}

#: What the connector names from ``cns.gate``. An older CNS lacks some of it.
_GATE_NAMES = ("GateChain", "GateOutcome", "GatePosition", "GateResult", "subject_digest")

#: The human inputs the retry probe supplies (see the module docstring).
_PROBE_BASIS = "repair probe: explicit human authorization"
_PROBE_ROOT = "repair probe: a human-established record standing as an evidence root"


class CnsNotInstalled(ImportError):
    """Raised by this module's CNS-facing functions when ``cns.gate`` is missing,
    or is too old to carry what the connector needs."""


class AttemptChanged(RuntimeError):
    """An :class:`Attempt`'s arguments were changed after it was built.

    What was digested is no longer what would run, so nothing runs.
    """


class PreflightError(RuntimeError):
    """CCC could not take a scratch copy of the store, so nothing was judged.

    The cause is chained. It is not a ``ValueError`` or a ``TypeError`` on
    purpose: a caller must not mistake "could not judge" for "CCC refused".
    """


def _cns_gate() -> ModuleType:
    """Import ``cns.gate`` on demand, or say exactly what is missing."""
    try:
        gate = importlib.import_module("cns.gate")
    except ImportError as exc:
        raise CnsNotInstalled(
            "ccc.cns_connector needs the CNS package (cns.gate), which is not "
            f"installed. Install it with: {INSTALL_HINT}. CCC itself works "
            "without it."
        ) from exc
    missing = [name for name in _GATE_NAMES if not hasattr(gate, name)]
    fields = getattr(getattr(gate, "GateResult", None), "__dataclass_fields__", {})
    if "subject_digest" not in fields:
        missing.append("GateResult.subject_digest")
    if missing:
        raise CnsNotInstalled(
            "ccc.cns_connector needs a newer CNS: the installed cns.gate lacks "
            f"{', '.join(missing)}. Install the pinned version with: "
            f"{INSTALL_HINT}."
        )
    return gate


def cns_available() -> bool:
    """Whether a CNS gate contract the connector can use is importable here."""
    try:
        _cns_gate()
    except CnsNotInstalled:
        return False
    return True


def _text(value: str) -> str:
    """``value`` as plain text the digest can encode, or ``TypeError``."""
    text = str(value)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise TypeError(
            "cannot bind a verdict to text that is not valid Unicode "
            "(a lone surrogate cannot be encoded for the digest)"
        ) from None
    return text


def _express(value: Any, depth: int = 0) -> Any:
    """Render one argument as content ``cns.gate.subject_digest`` accepts.

    Lossless or a ``TypeError``: a verdict bound to a guess is worth less than
    no verdict. What this returns, the digest can always compute. Needs no CNS.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        return _express(value.value, depth)
    if isinstance(value, Actor):
        return {
            "actor_id": _express(value.actor_id, depth),
            "kind": value.kind.value,
            "label": _express(value.label, depth),
        }
    if isinstance(value, int):
        if value.bit_length() > MAX_INT_BITS:
            raise TypeError(
                f"cannot bind a verdict to an integer wider than {MAX_INT_BITS} bits"
            )
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("cannot bind a verdict to NaN or an infinity")
        return float(value)
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, (Mapping, list, tuple)):
        if depth >= MAX_DEPTH:
            raise TypeError(
                f"cannot bind a verdict to content nested more than {MAX_DEPTH} "
                "levels deep (or to a cycle)"
            )
        if isinstance(value, Mapping):
            rendered = {
                _text(str(key)): _express(item, depth + 1) for key, item in value.items()
            }
            if len(rendered) != len(value):
                raise TypeError("mapping keys collide once stringified")
            return rendered
        return [_express(item, depth + 1) for item in value]
    raise TypeError(
        f"cannot bind a verdict to {type(value).__name__}; use str, int, float, "
        "bool, None, an Actor, an enum, or a mapping or sequence of those"
    )


def _bind(
    operation: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]
) -> inspect.BoundArguments:
    """``operation``'s real signature bound to the call, defaults applied.

    The first bound argument is ``self`` (``None``); the rest are named.
    """
    method = _FORWARDED.get(operation) or getattr(CCCSystem, operation)
    try:
        bound = inspect.signature(method).bind(None, *args, **kwargs)
    except TypeError as exc:
        raise TypeError(f"{operation}: {exc}") from exc
    bound.apply_defaults()
    return bound


def _judged_content(
    operation: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]
) -> dict[str, Any]:
    """The canonical mapping an attempted call is digested as."""
    bound = _bind(operation, args, kwargs)
    arguments = {
        name: _express(value) for name, value in list(bound.arguments.items())[1:]
    }
    return {"operation": operation, "arguments": arguments}


def _rebuild_attempt(
    operation: str, args: tuple[Any, ...], kwargs: dict[str, Any], subject: str
) -> "Attempt":
    return Attempt(operation, args, kwargs, subject)


@dataclass(frozen=True, eq=False)
class Attempt:
    """One attempted CCC transition: the thing the connector judges.

    Build it with :func:`attempt`. Its arguments are copied when it is built,
    and checked again before it runs, so what is digested is what is run. It can
    be copied and pickled; the copy is rebuilt, and so re-validated. Needs no CNS.
    """

    operation: str
    args: tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    subject: str = ""

    def __post_init__(self) -> None:
        if self.operation not in TRANSITIONS:
            raise ValueError(
                f"{self.operation!r} is not a transition the connector judges; "
                f"expected one of {', '.join(TRANSITIONS)}"
            )
        # Check the caller's own objects first: this is what refuses nesting
        # deep enough to overflow the stack in a copy, and cycles.
        _judged_content(self.operation, tuple(self.args), dict(self.kwargs))
        try:
            args = copy.deepcopy(tuple(self.args))
            kwargs = copy.deepcopy(dict(self.kwargs))
        except Exception as exc:
            raise TypeError(f"cannot copy the attempt's arguments: {exc}") from exc
        content = _judged_content(self.operation, args, kwargs)
        object.__setattr__(self, "args", args)
        object.__setattr__(self, "kwargs", MappingProxyType(kwargs))
        object.__setattr__(self, "subject", self.subject or self.operation)
        object.__setattr__(self, "_content", content)

    def __reduce__(self) -> tuple[Any, ...]:
        return (_rebuild_attempt, (self.operation, self.args, dict(self.kwargs), self.subject))

    @property
    def content(self) -> dict[str, Any]:
        """The canonical mapping that :func:`attempt_digest` digests (a copy)."""
        return copy.deepcopy(self._content)  # type: ignore[attr-defined]

    def _check_unchanged(self) -> None:
        try:
            now = _judged_content(self.operation, self.args, self.kwargs)
        except TypeError as exc:
            raise AttemptChanged(
                f"{self.operation}: the arguments changed after the attempt was built: {exc}"
            ) from exc
        if now != self._content:  # type: ignore[attr-defined]
            raise AttemptChanged(
                f"{self.operation}: the arguments changed after the attempt was built"
            )

    def run(self, system: CCCSystem) -> Any:
        """Perform the attempt on ``system``, for real, through CCC's own method.

        Raises :class:`AttemptChanged` if its arguments were changed since it
        was built.
        """
        self._check_unchanged()
        return getattr(system, self.operation)(*self.args, **self.kwargs)


def attempt(operation: str, /, *args: Any, **kwargs: Any) -> Attempt:
    """An :class:`Attempt` of ``CCCSystem.<operation>(*args, **kwargs)``.

    The label ``subject`` defaults to the operation name; use
    ``dataclasses.replace(att, subject="...")`` to name it.
    """
    return Attempt(operation, args, kwargs)


def attempt_digest(att: Attempt) -> str:
    """The digest a bound verdict on ``att`` carries.

    Pass it, with ``att.subject``, to ``GateResult.binds`` to check that a
    verdict was issued against exactly this attempted call.
    """
    return _cns_gate().subject_digest(att.content)


def to_cns_result(
    att: Attempt, outcome: BaseException | None, *, repairable: bool = False
) -> Any:
    """Translate what CCC did with ``att`` into a ``cns.gate.GateResult``.

    ``outcome`` is ``None`` when the call returned, or the exception it raised.
    Any exception that is not a constitutional refusal is treated as a refusal
    too: CCC errored, and an error is never a PASS.

    ``repairable`` is consulted only for a :class:`~ccc.errors.ConstitutionViolation`.
    Pass ``True`` only if a human supplying what the refusal asks for was shown to
    get the call admitted (:func:`judge` does that, on a scratch copy). The default
    fails closed: a constitutional refusal is ``TERMINAL_BREACH``.
    """
    if outcome is not None and not isinstance(outcome, BaseException):
        raise TypeError(
            "outcome must be None (the call returned) or the exception it raised; "
            f"got {type(outcome).__name__}"
        )
    gate = _cns_gate()
    if outcome is None:
        verdict, reason = gate.GateOutcome.PASS, PASS_REASON
    elif isinstance(outcome, ConstitutionViolation):
        verdict = (
            gate.GateOutcome.RETRY
            if repairable is True
            else gate.GateOutcome.TERMINAL_BREACH
        )
        reason = str(outcome)
    else:
        verdict = gate.GateOutcome.TERMINAL_BREACH
        reason = f"{type(outcome).__name__}: {outcome}"
    return gate.GateResult(
        gate=GATE_NAME,
        position=gate.GatePosition.ALPHA,
        outcome=verdict,
        reason=reason,
        subject=att.subject,
        subject_digest=gate.subject_digest(att.content),
    )


@contextmanager
def _scratches(system: CCCSystem) -> Iterator[Callable[[], CCCSystem]]:
    """Yield ``fresh()``: a throwaway copy of ``system`` per call, from one snapshot.

    The snapshot is CCC's own JSON round trip, held in a private temporary
    directory for as long as the ``with`` lasts.
    """
    with tempfile.TemporaryDirectory(prefix="ccc-preflight-") as tmp:
        path = Path(tmp) / "store.json"
        try:
            system.store.save(path)
        except Exception as exc:
            raise PreflightError(
                f"cannot judge: CCC cannot snapshot this store ({type(exc).__name__}: {exc})"
            ) from exc

        def fresh() -> CCCSystem:
            try:
                store = CCCStore.load(path)
                store.persistence_path = None
                return CCCSystem(store=store)
            except Exception as exc:
                raise PreflightError(
                    f"cannot judge: CCC cannot reload its snapshot ({type(exc).__name__}: {exc})"
                ) from exc

        yield fresh


def _repairable(fresh: Callable[[], CCCSystem], att: Attempt) -> bool:
    """Would CCC admit ``att`` once a human supplied what a refusal can ask for?

    Runs on a fresh scratch copy: the same operation, by the same actor, on the
    same target, with a non-empty authorization basis, the human event, and a
    human-established record as the evidence root added (see the module
    docstring). The actor is never changed, so a model that attempts a
    human-only operation is never repairable. Anything CCC refuses is not, and
    neither is a call CCC cannot run at all: an argument of the wrong type can
    crash the operation once the rule that refused the attempt no longer comes
    first, and that is no repair, so the verdict stays the fail-closed one. Only
    the probe is forgiving this way. The attempt itself is run by :func:`judge`,
    which lets such a crash propagate, as the real operation would.
    """
    system = fresh()
    human = Actor.human("repair-probe")
    try:
        root = system.ingest(
            _PROBE_ROOT,
            actor=human,
            epistemic_status=EpistemicStatus.HISTORICAL_RECORD,
            authorization_basis=_PROBE_BASIS,
        ).artifact_id
        bound = _bind(att.operation, att.args, att.kwargs)
        given = bound.arguments
        if "authorization_basis" in given and not given["authorization_basis"]:
            given["authorization_basis"] = _PROBE_BASIS
        if "human_event" in given:
            given["human_event"] = True
        if "evidence_ids" in given:
            given["evidence_ids"] = (*(given["evidence_ids"] or ()), root)
        if "source_material" in given:
            given["source_material"] = (root,)
        if att.operation == "classify":
            system.attach_evidence(
                given["artifact_id"], root, actor=human, rationale=_PROBE_ROOT
            )
        getattr(system, att.operation)(*bound.args[1:], **bound.kwargs)
    except Exception:
        # A scratch copy, so nothing is lost: not admitted, so not a repair.
        return False
    return True


def judge(system: CCCSystem, att: Attempt) -> Any:
    """Would CCC admit ``att`` now? A bound ``cns.gate.GateResult``, ALPHA.

    Runs the attempt on a scratch copy of ``system``'s store, so ``system`` is
    not changed in any way, including its audit trail and rule decisions. The
    refusals CCC uses are translated; a constitutional refusal is ``RETRY`` only
    if a human supplying what it asks for was shown, on a second scratch copy, to
    get the call admitted, and ``TERMINAL_BREACH`` otherwise. Any other exception
    propagates. Raises :class:`PreflightError` if the store cannot be copied and
    :class:`AttemptChanged` if ``att`` was altered after it was built.
    """
    _cns_gate()
    with _scratches(system) as fresh:
        try:
            att.run(fresh())
        except ConstitutionViolation as exc:
            return to_cns_result(att, exc, repairable=_repairable(fresh, att))
        except (CCCError, ValueError, KeyError) as exc:
            return to_cns_result(att, exc)
    return to_cns_result(att, None)


class CccGate:
    """A CCC gate that satisfies ``cns.gate.Gate``.

    ``check`` takes an :class:`Attempt` and returns :func:`judge`'s verdict at
    the ALPHA end: nothing has happened yet, and ``check`` makes nothing happen.
    """

    def __init__(self, system: CCCSystem) -> None:
        _cns_gate()  # fail here, at construction, not on first use
        self._system = system

    @property
    def name(self) -> str:
        return GATE_NAME

    @property
    def position(self) -> Any:
        return _cns_gate().GatePosition.ALPHA

    def check(self, candidate: object) -> Any:
        if not isinstance(candidate, Attempt):
            raise TypeError(
                "CCC gates judge an Attempt (see ccc.cns_connector.attempt); "
                f"got {type(candidate).__name__}"
            )
        return judge(self._system, candidate)


def cns_chain(system: CCCSystem) -> Any:
    """A ``cns.gate.GateChain`` holding CCC's gate in the ``alpha`` slot.

    ``omega`` stays empty: CCC has no outcome end. A consumer that wants a
    complete chain supplies that end from a repository that has one.
    """
    return _cns_gate().GateChain(alpha=(CccGate(system),))
