"""Run named tests (default: all) against a compiled library. Prints JSON results.

Executed in its own process by common.run_suite so crashes and coverage profiles are isolated.
Exit code 0 = all selected tests passed, 1 = at least one failed.
"""
import ctypes
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from suite import TESTS  # noqa: E402


def main() -> int:
    lib = ctypes.CDLL(sys.argv[1])
    for fn in ["validate_sample", "clamp_command", "rate_limit", "pipeline_step", "telemetry_dispatch"]:
        getattr(lib, fn).restype = ctypes.c_int
    names = sys.argv[2:] or list(TESTS)
    results = {}
    for name in names:
        try:
            TESTS[name](lib)
            results[name] = "pass"
        except AssertionError:
            results[name] = "fail"
        except Exception as exc:  # noqa: BLE001 - recorded, not hidden
            results[name] = "error:" + type(exc).__name__
    print(json.dumps({"results": results}))
    return 0 if all(v == "pass" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
