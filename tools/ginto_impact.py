"""Conservative Python import-graph test impact planner.

Fast *preflight* test selection. A full CI regression run is still required.
No model, arbitrary project API, or undeclared imported module is assumed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Any


class IncompleteGraph(Exception):
    """Static analysis cannot justify narrower preflight selection."""


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py")
                  if not any(q in {".git", ".venv", "venv", "node_modules", "__pycache__"} for q in p.relative_to(root).parts))


def _module_name(relative: Path) -> str:
    parts = relative.with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _import_target(name: str, mapping: dict[str, str]) -> str | None:
    """Return the closest local module/package for a qualified import."""
    while name:
        if name in mapping:
            return mapping[name]
        name = name.rpartition(".")[0]
    return None


def _imports(root: Path, path: Path, module_map: dict[str, str]) -> tuple[set[str], list[str]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    relative = path.relative_to(root)
    name = _module_name(relative)
    is_package = path.name == "__init__.py"
    package = name if is_package else name.rpartition(".")[0]
    dependencies: set[str] = set()
    hazards: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _import_target(alias.name, module_map)
                if target:
                    dependencies.add(target)
        elif isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                hazards.append(f"{relative}:{node.lineno} wildcard import")
            if node.level:
                prefix = package.split(".") if package else []
                # from .foo: level=1 means current package.
                trim = node.level - 1
                if trim >= len(prefix) + 1:
                    hazards.append(f"{relative}:{node.lineno} unresolved relative import")
                    continue
                prefix = prefix[:len(prefix)-trim] if trim else prefix
                base = ".".join([*prefix, *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            target = _import_target(base, module_map)
            if target:
                dependencies.add(target)
            # e.g. from package import submodule; retain both possible edges.
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                sub = module_map.get(candidate)
                if sub:
                    dependencies.add(sub)
        elif isinstance(node, ast.Call):
            fn = node.func
            symbol = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if symbol in {"__import__", "import_module", "exec", "eval"}:
                hazards.append(f"{relative}:{node.lineno} dynamic evaluation/import call")
    return dependencies, hazards


def plan(root: Path, changed: list[str], tests_dir: str = "tests") -> dict[str, Any]:
    """Produce auditable preflight selection or a full-run fallback.

    Conservative within the visible, statically imported Python subset; not a
    proof of safety for subprocesses, resources, reflection, generated files,
    runtime imports hidden behind aliases or cross-language calls.
    """
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    py = _files(root)
    rels = [str(p.relative_to(root).as_posix()) for p in py]
    tests_prefix = tests_dir.rstrip("/") + "/"
    tests = sorted(x for x in rels if x.startswith(tests_prefix) and Path(x).name.startswith("test_") and x.endswith(".py"))
    changed = sorted(set(Path(x).as_posix().removeprefix("./") for x in changed))
    if not changed:
        raise ValueError("Supply at least one changed path")
    if any(x.startswith("/") or x.startswith("../") or "/../" in x or x in {".", ".."} for x in changed):
        raise ValueError("Changed paths must be within project root")
    module_map = {_module_name(Path(r)): r for r in rels}
    edges: dict[str, set[str]] = {}
    hazards: list[str] = []
    hashes: dict[str, str] = {}
    for file in rels:
        src = root/file
        if src.is_symlink():
            hazards.append(f"Symlinked source: {file}")
            continue
        try:
            deps, problems = _imports(root, src, module_map)
            edges[file] = deps
            hazards.extend(problems)
            hashes[file] = _digest(src)
        except (SyntaxError, UnicodeError, OSError) as exc:
            hazards.append(f"Unparseable source {file}: {exc}")
    base = {"schema": 1, "mode": "PREVIEW_ONLY", "changed": changed,
            "all_tests": tests, "graph_edges": sum(map(len, edges.values())),
            "source_sha256": hashes, "hazards": sorted(hazards),
            "scope": "Python AST imports. Full suite must run before merge; no soundness guarantee."}
    def full(reason: str) -> dict[str, Any]:
        return {**base, "decision": "FULL_RETEST", "reason": reason,
                "selected_tests": tests, "traces": {t: [] for t in tests}}
    if not tests:
        return full("No recognizable Python test_*.py files")
    if hazards:
        return full("Unresolved dynamic/wildcard imports or parse failures")
    if any(c not in rels for c in changed):
        return full("Changed path outside analyzed Python files, new file or deletion")
    reverse: dict[str, set[str]] = {x: set() for x in rels}
    for importer, targets in edges.items():
        for target in targets:
            reverse.setdefault(target, set()).add(importer)
    reached = set(changed)
    queue = deque(changed)
    while queue:
        item = queue.popleft()
        for dependent in sorted(reverse.get(item, ())):
            if dependent not in reached:
                reached.add(dependent)
                queue.append(dependent)
    selected = sorted(set(tests) & reached)
    if not selected:
        return full("Changed Python source has no traced test; impact is unknown")
    traces = {}
    for test in selected:
        q = deque([(test, [test])])
        seen = set()
        while q:
            item, path = q.popleft()
            if item in seen:
                continue
            seen.add(item)
            if item in changed:
                traces[test] = path
                break
            for dep in sorted(edges.get(item, ())):
                q.append((dep, path+[dep]))
    return {**base, "decision": "IMPACTED_PREFLIGHT", "reason": "Visible transitive import path",
            "selected_tests": selected, "traces": traces}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--changed", nargs="+", required=True)
    parser.add_argument("--tests-dir", default="tests")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = plan(args.root, args.changed, args.tests_dir)
    content = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()