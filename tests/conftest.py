"""Skip the modules that need the CCCb text matcher when it is not installed.

Ten test modules import `cccb` when they load. Without the optional `match`
extra they used to fail collection. Now they are left out of the run, and the
run header says how many were left out, so the skip is visible.
"""

import importlib.util

MATCH_MODULES = [
    "test_determinism.py",
    "test_evidence_integrity_persistence.py",
    "test_external_finding.py",
    "test_matcher_boundary.py",
    "test_recurrence.py",
    "test_recurring_groups.py",
    "test_semantic.py",
    "test_semantic_hardening.py",
    "test_text_matching.py",
    "test_write_permission_doors.py",
]

collect_ignore = [] if importlib.util.find_spec("cccb") else list(MATCH_MODULES)


def pytest_report_header(config):
    if collect_ignore:
        return f"cccb not installed: {len(collect_ignore)} match-extra modules left out of the run"
    return None
