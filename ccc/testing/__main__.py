import json

from .harness import run_harness


if __name__ == "__main__":
    print(json.dumps(run_harness(), indent=2, sort_keys=True))
