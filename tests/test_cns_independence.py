"""CCC is independent of CNS, and these tests hold whether or not CNS is
installed. Each one runs in a fresh interpreter. Where CNS must be absent,
``sys.modules['cns'] = None`` makes any import of it fail, so the result does
not depend on what the test environment happens to contain. They never skip.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BLOCK = "import sys; sys.modules['cns'] = None; sys.modules['cns.gate'] = None\n"

PINNED_SHA = "3b465dbcc1a6a4ab6f1040f93d44483196abd737"


def _run(
    code: str, *, block: bool = True, ahead: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """``code`` in a fresh interpreter. ``ahead`` is a directory searched before
    anything installed, which is how a stand-in ``cns`` is put in front of a real one."""
    path = [str(ahead)] if ahead else []
    return subprocess.run(
        [sys.executable, "-c", (BLOCK if block else "") + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": os.pathsep.join([*path, str(ROOT)]), "PATH": ""},
        timeout=120,
    )


def _ok(done: subprocess.CompletedProcess[str]) -> None:
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"


def test_ccc_and_its_connector_import_with_cns_blocked():
    _ok(_run("import ccc, ccc.cns_connector; print('ok')"))


def test_importing_ccc_and_the_connector_loads_no_cns_even_when_cns_is_installed():
    """Not blocked on purpose: if CNS is present, a top-level import of it would
    show up here, which a blocked run cannot distinguish from a missing CNS."""
    _ok(
        _run(
            """
            import sys
            import ccc, ccc.cns_connector
            loaded = [m for m in sys.modules if m == "cns" or m.startswith("cns.")]
            assert not loaded, loaded
            print('ok')
            """,
            block=False,
        )
    )


def test_importing_ccc_does_not_load_the_connector():
    _ok(
        _run(
            """
            import sys
            import ccc
            assert "ccc.cns_connector" not in sys.modules
            print('ok')
            """,
            block=False,
        )
    )


def test_ccc_still_enforces_its_constitution_with_cns_blocked():
    _ok(
        _run(
            """
            from ccc import Actor, CCCSystem
            from ccc.demo import run_demo
            from ccc.errors import ConstitutionViolation

            result = run_demo()
            assert result["self_promotion_blocked"] is True
            assert result["constitution_valid"] is True

            system = CCCSystem()
            proposal = system.derive("machine inference", actor=Actor.model("m"))
            try:
                system.accept(
                    proposal.artifact_id,
                    actor=Actor.model("m"),
                    reason="consensus",
                    authorization_basis="machine vote",
                )
            except ConstitutionViolation as exc:
                assert exc.rule_id == "CCC-PROVENANCE-002"
            else:
                raise AssertionError("a model self-promoted")
            print('ok')
            """
        )
    )


def test_the_harness_still_runs_with_cns_blocked():
    _ok(
        _run(
            """
            from ccc.testing.harness import run_harness
            result = run_harness()
            assert result["total"] == 62
            assert result["failed"] == 0 and result["errors"] == 0
            print('ok')
            """
        )
    )


def test_connector_says_what_is_missing_when_cns_is_blocked():
    _ok(
        _run(
            """
            from ccc import Actor, CCCSystem
            from ccc.cns_connector import (
                CccGate, CnsNotInstalled, attempt, attempt_digest, cns_available,
                cns_chain, judge, to_cns_result,
            )

            assert cns_available() is False
            system = CCCSystem()
            att = attempt(
                "accept", "artifact_x", actor=Actor.human("h"), reason="r",
                authorization_basis="b",
            )
            calls = (
                lambda: judge(system, att),
                lambda: to_cns_result(att, None),
                lambda: attempt_digest(att),
                lambda: cns_chain(system),
                lambda: CccGate(system),
            )
            for call in calls:
                try:
                    call()
                except CnsNotInstalled as exc:
                    assert "pip install -e '.[cns]'" in str(exc)
                    assert isinstance(exc, ImportError)
                else:
                    raise AssertionError("no CnsNotInstalled")
            print('ok')
            """
        )
    )


def test_constructing_a_cns_gate_fails_at_construction_not_first_use():
    _ok(
        _run(
            """
            from ccc import CCCSystem
            from ccc.cns_connector import CccGate, CnsNotInstalled
            try:
                CccGate(CCCSystem())
            except CnsNotInstalled:
                print('ok')
            """
        )
    )


def test_the_parts_that_need_no_cns_work_with_cns_blocked():
    _ok(
        _run(
            """
            import copy, dataclasses, pickle
            from ccc import Actor, CCCSystem
            from ccc.cns_connector import (
                TRANSITIONS, AttemptChanged, attempt, cns_available,
            )

            human = Actor.human("h")
            att = attempt(
                "accept", artifact_id="artifact_x", actor=human, reason="r",
                authorization_basis="b",
            )
            same = attempt(
                "accept", "artifact_x", actor=human, reason="r",
                authorization_basis="b", evidence_ids=(),
            )
            assert att.content == same.content
            assert att.subject == "accept"
            assert dataclasses.replace(att, subject="review-7").subject == "review-7"
            assert all(callable(getattr(CCCSystem, name)) for name in TRANSITIONS)
            assert cns_available() is False

            # Attempt.run performs the real operation through CCC: no CNS involved.
            system = CCCSystem()
            proposal = system.derive("machine inference", actor=Actor.model("m"))
            real = attempt(
                "accept", proposal.artifact_id, actor=human, reason="reviewed",
                authorization_basis="explicit human adoption",
            )
            assert real.run(system).provenance_status.value == "USER_ACCEPTED"

            # Copies are rebuilt, and an attempt changed after it was built is not run.
            assert copy.deepcopy(att).content == att.content
            assert pickle.loads(pickle.dumps(att)).content == att.content
            edited = attempt(
                "canonicalize", "term_x", actor=human, source_material=["artifact_x"],
                reason="r", authorization_basis="b",
            )
            edited.kwargs["source_material"][0] = "artifact_y"
            try:
                edited.run(system)
            except AttemptChanged:
                pass
            else:
                raise AssertionError("an edited attempt ran")
            print('ok')
            """
        )
    )


def test_content_that_cannot_be_bound_is_refused_with_cns_blocked():
    _ok(
        _run(
            """
            import datetime
            from ccc import Actor
            from ccc.cns_connector import attempt

            human = Actor.human("h")
            deep = []
            for _ in range(400):
                deep = [deep]
            cycle = []
            cycle.append(cycle)
            bad = (
                {"confidence": float("nan")},
                {"confidence": float("inf")},
                {"metadata": {"when": datetime.datetime(2026, 1, 1)}},
                {"metadata": {"tags": {1, 2}}},
                {"metadata": {1: "a", "1": "b"}},
                {"reason": "a lone surrogate \\ud800"},
                {"presentation_priority": 10 ** 5000},
                {"metadata": {"deep": deep}},
                {"metadata": {"cycle": cycle}},
            )
            for extra in bad:
                try:
                    attempt("ingest", "c", actor=human, **extra)
                except TypeError:
                    pass
                else:
                    raise AssertionError(extra)
            for name in ("save", "derive", "no_such_method"):
                try:
                    attempt(name)
                except ValueError:
                    pass
                else:
                    raise AssertionError(name)
            print('ok')
            """
        )
    )


def _stand_in_cns(tmp_path: Path, *, with_digest: bool) -> Path:
    """A ``cns.gate`` that carries the connector's names, or all of them but the
    digest (what CNS looked like before it bound verdicts to what they judged)."""
    package = tmp_path / "cns"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    source = textwrap.dedent(
        """
        from dataclasses import dataclass

        class GatePosition:
            ALPHA = "alpha"
            OMEGA = "omega"

        class GateOutcome:
            PASS = "pass"
            RETRY = "retry"
            TERMINAL_BREACH = "terminal_breach"

        class GateChain:
            def __init__(self, alpha=(), omega=()):
                self.alpha, self.omega = alpha, omega
        """
    )
    if with_digest:
        source += textwrap.dedent(
            """
            @dataclass(frozen=True)
            class GateResult:
                gate: str
                position: object
                outcome: object
                reason: str = ""
                subject: str = ""
                subject_digest: str = ""

            def subject_digest(content):
                return "digest"
            """
        )
    else:
        source += textwrap.dedent(
            """
            @dataclass(frozen=True)
            class GateResult:
                gate: str
                position: object
                outcome: object
                reason: str = ""
            """
        )
    (package / "gate.py").write_text(source, encoding="utf-8")
    return tmp_path


def test_a_cns_too_old_to_bind_verdicts_is_not_available_and_says_why(tmp_path):
    _ok(
        _run(
            """
            from ccc import Actor, CCCSystem
            from ccc.cns_connector import (
                CccGate, CnsNotInstalled, attempt, cns_available, judge,
            )
            import cns.gate

            assert not hasattr(cns.gate, "subject_digest")  # the stand-in is in front
            assert cns_available() is False
            system = CCCSystem()
            att = attempt(
                "accept", "artifact_x", actor=Actor.human("h"), reason="r",
                authorization_basis="b",
            )
            for call in (lambda: judge(system, att), lambda: CccGate(system)):
                try:
                    call()
                except CnsNotInstalled as exc:
                    assert "subject_digest" in str(exc), str(exc)
                    assert "pip install -e '.[cns]'" in str(exc)
                else:
                    raise AssertionError("an old CNS was used")
            print('ok')
            """,
            block=False,
            ahead=_stand_in_cns(tmp_path, with_digest=False),
        )
    )


def test_a_cns_that_carries_what_the_connector_names_is_available(tmp_path):
    """The positive control for the test above: same stand-in, with the digest."""
    _ok(
        _run(
            """
            from ccc.cns_connector import cns_available
            import cns.gate

            assert hasattr(cns.gate, "subject_digest")
            assert cns_available() is True
            print('ok')
            """,
            block=False,
            ahead=_stand_in_cns(tmp_path, with_digest=True),
        )
    )


def test_the_preflight_error_is_not_mistaken_for_a_refusal():
    _ok(
        _run(
            """
            from ccc.cns_connector import (
                AttemptChanged, CnsNotInstalled, PreflightError,
            )
            from ccc.errors import CCCError
            for cls in (PreflightError, AttemptChanged):
                assert not issubclass(cls, (ValueError, TypeError, KeyError, CCCError))
            assert issubclass(CnsNotInstalled, ImportError)
            print('ok')
            """
        )
    )


def test_no_module_in_the_package_imports_cns():
    """CNS is reached only through ``importlib`` and a string, inside one helper."""
    offenders: list[str] = []
    for path in sorted((ROOT / "ccc").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            if any(name == "cns" or name.startswith("cns.") for name in names):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []


def test_the_package_declares_no_runtime_dependency():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == []
    assert "cns" in data["project"]["optional-dependencies"]


def test_the_cns_extra_is_pinned_to_the_reviewed_commit():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = data["project"]["optional-dependencies"]["cns"]
    assert extra == [
        f"cns @ git+https://github.com/wking53214/cns.git@{PINNED_SHA}"
    ]
    assert data["project"]["optional-dependencies"]["dev"] == ["pytest>=8"]
