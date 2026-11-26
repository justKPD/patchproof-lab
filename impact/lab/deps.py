"""Dependency discovery from real compiler artefacts.

Four independent sources, each produced by a real tool:
  1. Static call graph   - parsed from clang -O0 LLVM IR (direct calls; optional function-pointer edges)
  2. Constant def-use    - clang -ast-dump=json: which functions reference which header constants
  3. Test entry points   - Python ast of suite.py: which C ABI functions each test calls
  4. Dynamic coverage    - llvm-cov export of one profile per test, on the unchanged version
plus function line spans from the compiler's coverage mapping (used to map a change to a function).
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from common import BUILD, CPP, CXX, HEADERS, IMPACT, SOURCES, compile_library, demangle, run_suite, tool

DEFINE = re.compile(r"^define\s.*?@(\"?[\w.$]+\"?)\(")
DIRECT_CALL = re.compile(r"\bcall\b[^@%]*@([\w.$]+)\(")
INDIRECT_CALL = re.compile(r"\bcall\b[^@]*\s%[\w.]+\(")
GLOBAL_REF = re.compile(r"@([\w.$]+)")


def llvm_ir(src: Path) -> str:
    r = subprocess.run([CXX, "-std=c++17", "-O0", "-S", "-emit-llvm", "-o", "-", str(src)],
                       capture_output=True, text=True, check=True)
    return r.stdout


def static_call_graph(src_dir: Path = CPP) -> dict:
    """Return {'direct': {fn: [callees]}, 'address_taken': [...], 'indirect_callers': [...]} (demangled)."""
    direct: dict[str, set[str]] = {}
    address_taken: set[str] = set()
    indirect_callers: set[str] = set()
    for name in SOURCES:
        current = None
        for line in llvm_ir(src_dir / name).splitlines():
            m = DEFINE.match(line)
            if m:
                current = m.group(1).strip('"')
                direct.setdefault(current, set())
                continue
            if line.startswith("}"):
                current = None
                continue
            if current:
                for callee in DIRECT_CALL.findall(line):
                    if not callee.startswith("llvm."):
                        direct[current].add(callee)
                if INDIRECT_CALL.search(line):
                    indirect_callers.add(current)
            elif line.startswith("@") and "constant" in line or line.startswith("@") and "global" in line:
                # function addresses stored in global initialisers, e.g. a dispatch table
                for ref in GLOBAL_REF.findall(line.split("=", 1)[1]):
                    address_taken.add(ref)
    everything = set(direct) | {c for v in direct.values() for c in v} | address_taken | indirect_callers
    names = demangle(sorted(everything))
    address_taken = {a for a in address_taken if a in direct}  # only real functions
    return {
        "direct": {names[k]: sorted({names[c] for c in v}) for k, v in direct.items()},
        "address_taken": sorted(names[a] for a in address_taken),
        "indirect_callers": sorted(names[a] for a in indirect_callers),
    }


def reachable(graph: dict, entries: list[str], function_pointers: bool) -> set[str]:
    seen, stack = set(), list(entries)
    while stack:
        fn = stack.pop()
        if fn in seen:
            continue
        seen.add(fn)
        stack.extend(graph["direct"].get(fn, []))
        if function_pointers and fn in graph["indirect_callers"]:
            stack.extend(graph["address_taken"])  # conservative: any address-taken function
    return seen


def constant_uses(src_dir: Path = CPP) -> dict[str, list[str]]:
    """{constant_name: [functions referencing it]} from clang's JSON AST."""
    uses: dict[str, set[str]] = {}

    def walk(node, fn):
        if node.get("kind") == "FunctionDecl" and node.get("name"):
            fn = node["name"]
        if node.get("kind") == "DeclRefExpr":
            ref = node.get("referencedDecl", {})
            if ref.get("kind") == "VarDecl" and fn:
                uses.setdefault(ref["name"], set()).add(fn)
        for child in node.get("inner", []) or []:
            walk(child, fn)

    for name in SOURCES:
        r = subprocess.run([CXX, "-std=c++17", "-fsyntax-only", "-Xclang", "-ast-dump=json", str(src_dir / name)],
                           capture_output=True, text=True, check=True)
        walk(json.loads(r.stdout), None)
    return {k: sorted(v) for k, v in uses.items()}


def header_constants(src_dir: Path = CPP) -> dict[str, dict[int, str]]:
    """Line -> constant name for constexpr declarations in headers (non-executable entities)."""
    out = {}
    for h in HEADERS:
        rows = {}
        for i, line in enumerate((src_dir / h).read_text().splitlines(), 1):
            m = re.match(r"\s*constexpr\s+\w+\s+(\w+)\s*=", line)
            if m:
                rows[i] = m.group(1)
        out[h] = rows
    return out


def test_entries() -> dict[str, list[str]]:
    """Which ABI functions each test calls, from the Python AST of suite.py (static, not executed)."""
    tree = ast.parse((IMPACT / "lab" / "suite.py").read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("t_"):
            calls = {n.func.attr for n in ast.walk(node)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and isinstance(n.func.value, ast.Name) and n.func.value.id == "lib"}
            out[node.name] = sorted(calls)
    return out


def coverage_per_test(src_dir: Path = CPP) -> dict:
    """Run every test alone on an instrumented build; return covered functions and function spans."""
    lib = BUILD / "sut_cov.so"
    info = compile_library(src_dir, lib, coverage=True)
    if not info["ok"]:
        raise RuntimeError(info["stderr"])
    from suite import TESTS
    covered: dict[str, list[str]] = {}
    spans: dict[str, dict] = {}
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        for name in TESTS:
            raw, data = Path(tmp) / f"{name}.profraw", Path(tmp) / f"{name}.profdata"
            res = run_suite(lib, [name], env={"LLVM_PROFILE_FILE": str(raw)})
            if res["crashed"] or res["results"].get(name) != "pass":
                raise RuntimeError(f"coverage run failed for {name}")
            subprocess.run([tool("llvm-profdata"), "merge", "-o", str(data), str(raw)], check=True)
            exp = subprocess.run([tool("llvm-cov"), "export", str(lib), f"-instr-profile={data}", "-format=text"],
                                 capture_output=True, text=True, check=True)
            functions = json.loads(exp.stdout)["data"][0]["functions"]
            names = demangle([f["name"] for f in functions])
            covered[name] = sorted({names[f["name"]] for f in functions if f["count"] > 0})
            if not spans:
                for f in functions:
                    first = f["regions"][0]  # [lineStart, colStart, lineEnd, colEnd, count, fileID, ...]
                    spans[names[f["name"]]] = {"file": Path(f["filenames"][first[5]]).name,
                                               "start": first[0], "end": first[2]}
    return {"covered": covered, "spans": spans, "seconds": time.perf_counter() - t0}


def discover(src_dir: Path = CPP) -> dict:
    t0 = time.perf_counter()
    graph = static_call_graph(src_dir)
    t_static = time.perf_counter() - t0
    cov = coverage_per_test(src_dir)
    return {
        "call_graph": graph,
        "constant_uses": constant_uses(src_dir),
        "header_constants": header_constants(src_dir),
        "test_entries": test_entries(),
        "coverage": cov["covered"],
        "function_spans": cov["spans"],
        "timing_seconds": {"static_call_graph": t_static, "dynamic_coverage": cov["seconds"]},
    }


if __name__ == "__main__":
    print(json.dumps(discover(), indent=1)[:4000])
