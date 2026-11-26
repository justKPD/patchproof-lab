"""Reproducible authored three-module regression-selection experiment.

One controlled fixture: demonstrates a hidden regression missed by direct-only
selection and detected by transitive import selection. No real-world rates.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ginto_impact import plan

SOURCES = {
    "sensor.py": "def fresh(age: int, timeout: int) -> bool:\n    return age < timeout\n",
    "control.py": "from sensor import fresh\n\ndef command(age: int, timeout: int) -> int:\n    return 50 if fresh(age, timeout) else 0\n",
    "api.py": "from control import command\n\ndef get_command(age: int, timeout: int) -> dict:\n    return {'accepted_command': command(age, timeout)}\n",
    "unrelated.py": "def version() -> int:\n    return 1\n",
    "tests/__init__.py": "",
    "tests/test_nominal.py": "import unittest\nfrom sensor import fresh\nclass Nominal(unittest.TestCase):\n    def test_known_good(self): self.assertTrue(fresh(9, 10))\n",
    "tests/test_downstream.py": "import unittest\nfrom api import get_command\nclass Downstream(unittest.TestCase):\n    def test_expiration_boundary(self): self.assertEqual(get_command(10, 10)['accepted_command'], 0)\n",
    "tests/test_unrelated.py": "import unittest\nfrom unrelated import version\nclass Unrelated(unittest.TestCase):\n    def test_version(self): self.assertEqual(version(), 1)\n",
}


def write_fixture(root: Path, buggy: bool = False) -> None:
    for filename, content in SOURCES.items():
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if buggy and filename == "sensor.py":
            content = content.replace("age < timeout", "age <= timeout")
        path.write_text(content, encoding="utf8")


def run_tests(root: Path, selected: list[str]) -> dict:
    """Execute independent unittest processes so no module cache survives."""
    results = []
    for relative in selected:
        module = relative.replace("/", ".").removesuffix(".py")
        process = subprocess.run([sys.executable, "-m", "unittest", module, "-v"],
                                 cwd=root, capture_output=True, text=True, timeout=20,
                                 env={**os.environ, "PYTHONPATH": str(root)})
        results.append({"test": relative, "passed": process.returncode == 0,
                        "returncode": process.returncode, "output": (process.stderr or process.stdout)[-1200:]})
    return {"selected": selected, "failed": [r["test"] for r in results if not r["passed"]],
            "results": results}


def experiment() -> dict:
    with tempfile.TemporaryDirectory(prefix="patchproof-ginto-") as d:
        root = Path(d)
        write_fixture(root)
        clean_plan = plan(root, ["sensor.py"])
        all_tests = clean_plan["all_tests"]
        clean = run_tests(root, all_tests)
        assert not clean["failed"], clean
        write_fixture(root, buggy=True)
        after = plan(root, ["sensor.py"])
        # Deliberately incomplete policy: test imports sensor.py directly.
        direct_only = ["tests/test_nominal.py"]
        selected = after["selected_tests"]
        direct = run_tests(root, direct_only)
        transitive = run_tests(root, selected)
        complete = run_tests(root, all_tests)
        detection = lambda result: bool(result["failed"])
        assert after["decision"] == "IMPACTED_PREFLIGHT"
        assert not detection(direct), "Negative-control direct selection unexpectedly caught regression"
        assert detection(transitive) and detection(complete)
        return {
            "schema": 1, "fixture": "authored Python 3-module chain; boundary bug '<' to '<='",
            "changed": ["sensor.py"], "baseline": {"tests_run": len(all_tests), "failures": clean["failed"]},
            "direct_only": {"tests_run": len(direct_only), "failures": direct["failed"], "detected": detection(direct)},
            "transitive": {"tests_run": len(selected), "failures": transitive["failed"], "detected": detection(transitive), "traces": after["traces"]},
            "full": {"tests_run": len(all_tests), "failures": complete["failed"], "detected": detection(complete)},
            "caveats": ["One authored, controlled Python example; not generalized safety or efficiency evidence.",
                        "Direct-only is a deliberately weak negative control.",
                        "The AST import graph is incomplete for dynamic dependencies; full CI regression is still required."]
        }


def main():
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = experiment()
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(encoded+"\n",encoding="utf8")
    print(encoded)


if __name__ == "__main__":
    main()