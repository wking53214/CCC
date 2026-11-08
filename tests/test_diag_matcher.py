"""Temporary diagnostic: show what the matcher subprocess sees on the CI runner. Not for merge."""

import subprocess
import sys


def test_diag_matcher_subprocess():
    code = (
        "import sys, cccb\n"
        "print('VERSION', sys.version.split()[0])\n"
        "print('CCCB_FILE', cccb.__file__)\n"
        "print('PATH0', sys.path[:4])\n"
        "from cccb import TextMatcher\n"
        "m = TextMatcher()\n"
        "text = 'ledger hashing chain digest rolling block verification audit trail'\n"
        "for i in ['delta', 'gamma', 'alpha', 'echo', 'bravo', 'charlie']:\n"
        "    m.add(i, text)\n"
        "print('RESULT1', m.recurrence_of('ledger hashing chain digest rolling block verification audit trail extra')[0])\n"
        "print('RESULT2', m.recurrence_of(text)[2][0][0])\n"
    )
    for seed in (0, 1):
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                              env={"PYTHONHASHSEED": str(seed)})
        print(f"SEED {seed} RC {done.returncode}")
        print("STDOUT<<" + done.stdout + ">>")
        print("STDERR<<" + done.stderr[-800:] + ">>")
    assert False, "diagnostic run: see the printed output"
