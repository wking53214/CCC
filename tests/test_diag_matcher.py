"""Temporary diagnostic: show what the matcher subprocess sees on the CI runner. Not for merge."""

import subprocess
import sys


def test_diag_matcher_subprocess():
    code = (
        "import sys, hashlib, pathlib, cccb\n"
        "print('VERSION', sys.version.split()[0])\n"
        "base = pathlib.Path(cccb.__file__).parent\n"
        "for name in ['recurrence.py', 'matcher.py', 'matching.py']:\n"
        "    print('SHA', name, hashlib.sha256((base / name).read_bytes()).hexdigest()[:12])\n"
        "print('BOILER', sorted(p.name for p in (base / 'known_boilerplate').glob('*.txt')))\n"
        "from cccb import TextMatcher\n"
        "m = TextMatcher()\n"
        "text = 'ledger hashing chain digest rolling block verification audit trail'\n"
        "for i in ['delta', 'gamma', 'alpha', 'echo', 'bravo', 'charlie']:\n"
        "    m.add(i, text)\n"
        "print('FULL', m.recurrence_of(text))\n"
    )
    for seed in (0, 1):
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                              env={"PYTHONHASHSEED": str(seed)})
        print(f"SEED {seed} RC {done.returncode} OUT {done.stdout} ERR {done.stderr[-400:]}")
    assert False, "diagnostic run: see the printed output"
