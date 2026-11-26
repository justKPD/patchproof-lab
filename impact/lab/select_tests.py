"""Regression test selection techniques compared in the experiment.

Every technique receives the same inputs: the change location (file, line) and the
dependency facts discovered on the UNCHANGED version. None sees the test outcomes
of the change it is selecting for (no leakage). The learned technique is trained
only on other changes (cross-validation in experiment_rts.py).
"""
from __future__ import annotations

import re

from common import CPP
from deps import reachable
from suite import DECLARED, TESTS


def changed_entity(change: dict, facts: dict) -> dict:
    """Map a changed line to the enclosing function, or a non-executable global/constant."""
    for fn, span in facts["function_spans"].items():
        if span["file"] == change["file"] and span["start"] <= change["line"] <= span["end"]:
            return {"kind": "function", "name": fn}
    line = (CPP / change["file"]).read_text().splitlines()[change["line"] - 1]
    m = re.search(r"\b(k\w+)\s*(\[|=)", line)
    if m:
        return {"kind": "global", "name": m.group(1)}
    return {"kind": "unknown", "name": None}


def users_of_global(name: str, facts: dict) -> set[str]:
    return set(facts["constant_uses"].get(name, []))


def retest_all(change, facts):
    return set(TESTS)


def declared_manifest(change, facts):
    return {t for t, files in DECLARED.items() if change["file"] in files}


def _static(change, facts, function_pointers):
    ent = changed_entity(change, facts)
    targets = {ent["name"]} if ent["kind"] == "function" else users_of_global(ent["name"], facts) if ent["kind"] == "global" else None
    if targets is None:
        return set(TESTS)  # cannot localise -> fail safe
    return {t for t, entries in facts["test_entries"].items()
            if reachable(facts["call_graph"], entries, function_pointers) & targets}


def static_call_graph(change, facts):
    return _static(change, facts, function_pointers=False)


def static_with_fn_pointers(change, facts):
    return _static(change, facts, function_pointers=True)


def dynamic_coverage(change, facts):
    """Ekstazi-style dynamic dependencies, at function granularity, from per-test coverage."""
    ent = changed_entity(change, facts)
    if ent["kind"] != "function":
        return set()  # non-executable entities never appear in coverage: the known blind spot
    return {t for t, fns in facts["coverage"].items() if ent["name"] in fns}


def hybrid(change, facts):
    """Recommended: dynamic coverage, plus static def-use for non-executable changes,
    plus conservative static fallback when the changed function is covered by no test."""
    ent = changed_entity(change, facts)
    if ent["kind"] == "function":
        dyn = dynamic_coverage(change, facts)
        return dyn if dyn else static_with_fn_pointers(change, facts)
    if ent["kind"] == "global":
        users = users_of_global(ent["name"], facts)
        return {t for t, fns in facts["coverage"].items() if set(fns) & users} or static_with_fn_pointers(change, facts)
    return set(TESTS)


TECHNIQUES = {
    "retest_all": retest_all,
    "declared_manifest": declared_manifest,
    "static_call_graph": static_call_graph,
    "static_with_fn_pointers": static_with_fn_pointers,
    "dynamic_coverage": dynamic_coverage,
    "hybrid": hybrid,
}


def features(change: dict, test: str, facts: dict, history: dict) -> list[float]:
    """Feature vector for the learned (Facebook-style predictive) selector."""
    ent = changed_entity(change, facts)
    graph = facts["call_graph"]
    entries = facts["test_entries"][test]
    naive = reachable(graph, entries, False)
    covered = set(facts["coverage"][test])
    target = {ent["name"]} if ent["kind"] == "function" else users_of_global(ent["name"], facts) if ent["kind"] == "global" else set()
    return [
        1.0 if target & covered else 0.0,
        1.0 if target & naive else 0.0,
        1.0 if change["file"] in DECLARED[test] else 0.0,
        1.0 if change["file"].endswith(".h") else 0.0,
        float(len(covered)),
        history.get(test, 0.0),  # failure rate of this test on training changes
        1.0 if change["operator"] == "CRP" else 0.0,
        1.0 if change["operator"] == "ROR" else 0.0,
    ]


FEATURE_NAMES = ["covers_changed", "static_reaches_changed", "declared_same_file", "header_change",
                 "coverage_size", "historical_failure_rate", "op_constant", "op_relational"]
