"""Does the same evidence always produce the same outcome?

CCC mints random ids and wall-clock timestamps, so two runs never match byte
for byte. What must match is everything else: stages, links, counts, the
order of ordered collections, and how a state file round-trips. Each scenario
runs in fresh interpreters under different hash seeds, with the ids and
timestamps replaced by their order of first appearance.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

from ccc import Actor, AnalysisStage, CCCSystem
from cccb import TextMatcher

ROOT = Path(__file__).resolve().parents[1]

# The same eight concepts in a different order each time: never a duplicate,
# always a recurrence, and the recurrence candidates tie on score.
SCENARIO = r'''
import json, re, sys
from dataclasses import dataclass
from typing import Optional, Tuple
from ccc import Actor, CCCSystem
from cccb import TextMatcher

@dataclass(frozen=True)
class F:
    conclusion: str
    method: str = "ecology.search"
    source_material: Tuple[str, ...] = ("notes.md",)
    confidence: Optional[float] = 0.6
    verified: bool = True
    evidence: Tuple[Tuple[str, str], ...] = ()

texts = [
    "ledger hashing digest chain rolling block audit trail verification alpha",
    "verification audit trail block rolling chain digest hashing ledger bravo",
    "trail hashing verification ledger audit chain block digest rolling charlie",
    "block ledger rolling trail digest audit hashing chain verification delta",
    "rolling digest ledger verification trail hashing block chain audit echo",
]
s = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
m = Actor.model("ecology")
for t in texts:
    s.record_external_finding(F(t), actor=m)
s.record_external_finding(F(texts[0]), actor=m)   # a re-run: duplicate
s.record_external_finding(F(texts[2]), actor=m)   # another re-run
s.record_external_finding(F("an unrelated note on carburettor tuning for vintage engines"), actor=m)

text = json.dumps(s.store.snapshot(), sort_keys=True, indent=1)
seen = {}
for did in s.store.discoveries:          # creation order, not the order sorted keys happen to show
    seen[did] = "ID%d" % len(seen)
def ordinal(match):
    return seen.setdefault(match.group(0), "ID%d" % len(seen))
text = re.sub(r"[a-z_]+_[0-9a-f]{32}", ordinal, text)
text = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+\+00:00", "T", text)
print(json.dumps(json.loads(text), sort_keys=True, indent=1))   # keys named by ordinal now, so sort again
'''


def _run(seed: int) -> str:
    done = subprocess.run([sys.executable, "-I", "-c", SCENARIO], capture_output=True, text=True,
                          cwd=ROOT, env={"PYTHONHASHSEED": str(seed), "PYTHONPATH": str(ROOT)})
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_the_whole_evidence_path_gives_one_outcome_under_every_hash_seed():
    outputs = {seed: _run(seed) for seed in (0, 1, 2, 3, 5, 8, 13)}
    first = outputs[0]
    assert '"stage": "PATTERN"' in first and "duplicate detection" in first  # the scenario did something
    assert all(out == first for out in outputs.values())


def test_the_same_evidence_twice_in_one_process_gives_one_outcome():
    def run() -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(SCENARIO, "scenario", "exec"), {})  # noqa: S102 - our own constant
        return out.getvalue()
    assert run() == run()


FINDING = dict(method="ecology.search", source_material=("b.md", "a.md", "c.md"), confidence=0.4, verified=True)


RECURRING = [
    "ledger hashing digest chain rolling block audit trail verification alpha",
    "verification audit trail block rolling chain digest hashing ledger bravo",
    "trail hashing verification ledger audit chain block digest rolling charlie",
    "block ledger rolling trail digest audit hashing chain verification delta",
]


class _Finding:
    def __init__(self, conclusion, evidence=()):
        self.conclusion, self.evidence = conclusion, evidence
        self.__dict__.update(FINDING)


def test_ordered_collections_keep_their_order_and_are_not_sorted_for_tidiness():
    system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
    evidence = (("z.md", "last alphabetically, first in order"), ("a.md", "first alphabetically, second in order"))
    record = system.record_external_finding(_Finding("Order matters here.", evidence), actor=Actor.model("e"))
    assert record.source_material == ("b.md", "a.md", "c.md")
    assert record.supporting_evidence == ("z.md: last alphabetically, first in order",
                                          "a.md: first alphabetically, second in order")


def test_a_saved_state_reloads_to_the_same_state_and_saves_to_the_same_bytes(tmp_path):
    system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
    actor = Actor.model("e")
    for text in (RECURRING[0], RECURRING[1], RECURRING[0]):
        system.record_external_finding(_Finding(text, (("s.md", text),)), actor=actor)
    system.ingest("A human note.", actor=Actor.human())

    first, second = tmp_path / "first.json", tmp_path / "second.json"
    system.save(first)
    system.save(second)
    assert first.read_bytes() == second.read_bytes()

    reloaded = CCCSystem.load(first, text_matcher=TextMatcher(), private_source_markers=())
    assert reloaded.store.snapshot() == system.store.snapshot()
    reloaded.save(second)
    assert second.read_bytes() == first.read_bytes()

    again = CCCSystem.load(second, text_matcher=TextMatcher(), private_source_markers=())
    again.save(tmp_path / "third.json")
    assert (tmp_path / "third.json").read_bytes() == first.read_bytes()


def test_the_reloaded_matcher_measures_the_way_the_live_one_did(tmp_path):
    system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
    actor = Actor.model("e")
    ids = [system.record_external_finding(_Finding(t), actor=actor).discovery_id for t in RECURRING[:3]]
    path = system.save(tmp_path / "state.json")
    reloaded = CCCSystem.load(path, text_matcher=TextMatcher(), private_source_markers=())
    live = system.record_external_finding(_Finding(RECURRING[3]), actor=actor)
    after = reloaded.record_external_finding(_Finding(RECURRING[3]), actor=actor)
    assert set(live.relationships) <= set(ids) and set(after.relationships) <= set(ids)
    assert system.store.discoveries[live.relationships[-1]].stage is AnalysisStage.PATTERN
    assert reloaded.store.discoveries[after.relationships[-1]].stage is AnalysisStage.PATTERN
    assert live.relationships[-1] == after.relationships[-1] == ids[0]


def test_the_state_file_is_canonical_json(tmp_path):
    system = CCCSystem()
    system.ingest("A human note.", actor=Actor.human())
    path = system.save(tmp_path / "state.json")
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == json.loads(json.dumps(json.loads(text), sort_keys=True))
    assert re.search(r'^\{\n  "', text)
    assert list(json.loads(text)) == sorted(json.loads(text))


def test_stage_progress_is_the_same_whatever_order_independent_findings_arrive_in():
    results = set()
    for order in (RECURRING, list(reversed(RECURRING)), RECURRING[1:] + RECURRING[:1]):
        system = CCCSystem(text_matcher=TextMatcher(), private_source_markers=())
        for text in order:
            system.record_external_finding(_Finding(text), actor=Actor.model("e"))
        (group,) = system.recurring_groups()
        results.add((group.stage, group.occurrence_count, len(group.duplicates)))
    assert results == {(AnalysisStage.PATTERN, 4, 0)}
