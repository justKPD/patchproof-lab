"""Shared paths and build helpers for the impact lab.

Everything here runs real tools (clang++, llvm-profdata, llvm-cov). Nothing is simulated.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

IMPACT = Path(__file__).resolve().parents[1]
ROOT = IMPACT.parent
CPP = IMPACT / "cpp"
RESULTS = IMPACT / "results"
BUILD = IMPACT / ".build"
SOURCES = ["sensor.cpp", "limiter.cpp", "rate.cpp", "pipeline.cpp", "telemetry.cpp"]
HEADERS = ["units.h", "config.h"]
ALL_FILES = SOURCES + HEADERS


def tool(name: str) -> str:
    """Find an LLVM tool, allowing versioned names (llvm-cov-18) and env overrides."""
    env = os.environ.get(name.upper().replace("-", "_"))
    if env:
        return env
    for candidate in [name, f"{name}-18", f"{name}-19", f"{name}-17"]:
        found = shutil.which(candidate)
        if found:
            return found
    raise FileNotFoundError(f"{name} not found; set {name.upper().replace('-', '_')}")


CXX = os.environ.get("CXX_IMPACT", "clang++")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_digest(directory: Path = CPP) -> str:
    h = hashlib.sha256()
    for name in ALL_FILES:
        h.update(name.encode())
        h.update((directory / name).read_bytes())
    return h.hexdigest()


def compile_library(src_dir: Path, out: Path, coverage: bool = False) -> dict:
    """Compile the five translation units into one shared library."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [CXX, "-std=c++17", "-O0", "-shared", "-fPIC", "-Wall", "-Wextra"]
    if coverage:
        cmd += ["-fprofile-instr-generate", "-fcoverage-mapping"]
    cmd += [str(src_dir / s) for s in SOURCES] + ["-o", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return {"ok": r.returncode == 0, "stderr": r.stderr[-4000:], "returncode": r.returncode}


def run_suite(library: Path, tests: list[str] | None = None, env: dict | None = None, timeout: int = 30) -> dict:
    """Run the system test suite in a separate process (crash isolation)."""
    args = [sys.executable, "-I", str(IMPACT / "lab" / "run_suite.py"), str(library)]
    if tests:
        args += tests
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})})
    if r.returncode not in (0, 1):
        # Process crashed (e.g. signal). Every requested test counts as failed.
        return {"crashed": True, "stderr": r.stderr[-2000:], "results": {}}
    return {"crashed": False, "results": json.loads(r.stdout)["results"]}


def demangle(names: list[str]) -> dict[str, str]:
    """Map mangled coverage names (incl. 'file.cpp:' prefix for statics) to plain function names."""
    stripped = [n.split(":", 1)[1] if ":" in n and not n.startswith("_Z") else n for n in names]
    filt = shutil.which("llvm-cxxfilt") or shutil.which("llvm-cxxfilt-18") or shutil.which("c++filt")
    out = subprocess.run([filt], input="\n".join(stripped), capture_output=True, text=True).stdout.splitlines()
    return {orig: d.split("(")[0].strip() for orig, d in zip(names, out)}


def temp_copy_of_sources() -> Path:
    d = Path(tempfile.mkdtemp(prefix="impact-src-"))
    for name in ALL_FILES:
        shutil.copy2(CPP / name, d / name)
    return d


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n", encoding="utf8")
