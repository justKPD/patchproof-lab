"""Experiment 1: which tests must rerun after a change, and which technique finds them?

Ground truth: for every compilable mutant, the FULL suite is executed (retest-all).
A technique is *safe* on a change if it selects every test that actually fails.
Metrics are computed over identical changes for all techniques.
"""
from __future__ import annotations

import json
import random
import shutil
import sqlite3
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, CPP, RESULTS, compile_library, run_suite, source_digest, temp_copy_of_sources, write_json  # noqa: E402
from deps import discover  # noqa: E402
from mutate import generate, materialise  # noqa: E402
from select_tests import FEATURE_NAMES, TECHNIQUES, changed_entity, features  # noqa: E402
from suite import TESTS  # noqa: E402


def evaluate_mutant(m: dict) -> dict:
    d = temp_copy_of_sources()
    try:
        materialise(m, d)
        lib = BUILD / "mutants" / f"{m['id']}.so"
        build = compile_library(d, lib)
        if not build["ok"]:
            return {**m, "compiled": False}
        res = run_suite(lib)
        crashed_tests = []
        if res["crashed"]:
            # A crash in one test must not be attributed to all tests: isolate each test.
            results = {}
            for t in TESTS:
                single = run_suite(lib, [t])
                results[t] = "crash" if single["crashed"] else single["results"][t]
                if single["crashed"]:
                    crashed_tests.append(t)
        else:
            results = res["results"]
        lib.unlink(missing_ok=True)
        failing = sorted(t for t, v in results.items() if v != "pass")
        return {**m, "compiled": True, "crashed": bool(crashed_tests), "crashed_tests": crashed_tests, "failing": failing}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def score(selected: set, failing: list) -> dict:
    f = set(failing)
    return {"selected": len(selected), "detected": bool(selected & f) if f else None,
            "safe": f <= selected if f else None, "missed": sorted(f - selected)}


def learned_selector(changes, facts, folds_by, seed=7):
    """Logistic-regression predictive selection (Machalica et al. 2019 style), cross-validated.
    Threshold per fold = largest probability cut-off giving >=95% failing-test recall on TRAIN pairs."""
    from sklearn.linear_model import LogisticRegression
    groups = sorted({folds_by(c) for c in changes})
    out = {}
    for g in groups:
        train = [c for c in changes if folds_by(c) != g]
        test = [c for c in changes if folds_by(c) == g]
        n = max(1, len(train))
        history = {t: sum(t in c["failing"] for c in train) / n for t in TESTS}
        X, y = [], []
        for c in train:
            for t in TESTS:
                X.append(features(c, t, facts, history))
                y.append(1 if t in c["failing"] else 0)
        if len(set(y)) < 2:
            for c in test:
                out[c["id"]] = set(TESTS)  # no positive examples: fail safe
            continue
        model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed).fit(X, y)
        probs = model.predict_proba(X)[:, 1]
        pos = sorted(p for p, label in zip(probs, y) if label)
        cut = pos[int(0.05 * len(pos))] if pos else 0.5
        for c in test:
            p = model.predict_proba([features(c, t, facts, history) for t in TESTS])[:, 1]
            out[c["id"]] = {t for t, pr in zip(TESTS, p) if pr >= cut}
    return out


def summarise(name, per_change, changes):
    faulty = [c for c in changes if c["failing"]]
    rows = [per_change[c["id"]] for c in changes]
    frows = [per_change[c["id"]] for c in faulty]
    total_fail = sum(len(c["failing"]) for c in faulty)
    caught = sum(len(c["failing"]) - len(per_change[c["id"]]["missed"]) for c in faulty)
    return {
        "technique": name,
        "mean_tests_selected": statistics.mean(r["selected"] for r in rows),
        "mean_fraction_selected": statistics.mean(r["selected"] for r in rows) / len(TESTS),
        "faulty_changes": len(faulty),
        "faulty_changes_detected": sum(1 for r in frows if r["detected"]),
        "faulty_changes_fully_safe": sum(1 for r in frows if r["safe"]),
        "failing_test_recall": caught / total_fail if total_fail else None,
        "missed_changes": [c["id"] for c in faulty if not per_change[c["id"]]["detected"]],
    }


def to_sqlite(db: Path, facts, changes, selections, summaries):
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE tests(name TEXT PRIMARY KEY, declared_file TEXT);
    CREATE TABLE coverage(test TEXT, function TEXT);
    CREATE TABLE call_edges(caller TEXT, callee TEXT, kind TEXT);
    CREATE TABLE changes(id TEXT PRIMARY KEY, file TEXT, line INT, operator TEXT, entity_kind TEXT,
                         entity TEXT, before TEXT, after TEXT, compiled INT, crashed INT);
    CREATE TABLE outcomes(change_id TEXT, test TEXT, failed INT);
    CREATE TABLE selections(technique TEXT, change_id TEXT, test TEXT);
    CREATE TABLE technique_summary(technique TEXT PRIMARY KEY, mean_fraction_selected REAL,
                         faulty_changes INT, detected INT, fully_safe INT, failing_test_recall REAL);
    """)
    from suite import DECLARED
    con.executemany("INSERT INTO tests VALUES(?,?)", [(t, DECLARED[t][0]) for t in TESTS])
    con.executemany("INSERT INTO coverage VALUES(?,?)", [(t, f) for t, fs in facts["coverage"].items() for f in fs])
    g = facts["call_graph"]
    edges = [(a, b, "direct") for a, bs in g["direct"].items() for b in bs]
    edges += [(a, b, "function_pointer") for a in g["indirect_callers"] for b in g["address_taken"]]
    con.executemany("INSERT INTO call_edges VALUES(?,?,?)", edges)
    for c in changes:
        e = changed_entity(c, facts) if c["compiled"] else {"kind": None, "name": None}
        con.execute("INSERT INTO changes VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (c["id"], c["file"], c["line"], c["operator"], e["kind"], e["name"], c["before"], c["after"],
                     int(c["compiled"]), int(c.get("crashed", False))))
        if c["compiled"]:
            con.executemany("INSERT INTO outcomes VALUES(?,?,?)", [(c["id"], t, int(t in c["failing"])) for t in TESTS])
    for tech, per in selections.items():
        con.executemany("INSERT INTO selections VALUES(?,?,?)", [(tech, cid, t) for cid, ts in per.items() for t in sorted(ts)])
    con.executemany("INSERT INTO technique_summary VALUES(?,?,?,?,?,?)",
                    [(s["technique"], s["mean_fraction_selected"], s["faulty_changes"], s["faulty_changes_detected"],
                      s["faulty_changes_fully_safe"], s["failing_test_recall"]) for s in summaries])
    con.commit()
    con.close()


def main():
    t0 = time.perf_counter()
    facts = discover()
    all_mutants = generate()
    with ThreadPoolExecutor(max_workers=8) as pool:
        evaluated = list(pool.map(evaluate_mutant, all_mutants))
    changes = [c for c in evaluated if c["compiled"]]
    for c in changes:
        c["entity"] = changed_entity(c, facts)

    selections, per_change = {}, {}
    for name, fn in TECHNIQUES.items():
        t = time.perf_counter()
        sel = {c["id"]: fn(c, facts) for c in changes}
        selections[name] = sel
        per_change[name] = {"seconds": time.perf_counter() - t,
                            "scores": {c["id"]: score(sel[c["id"]], c["failing"]) for c in changes}}

    rnd = random.Random(42)
    fold_of = {c["id"]: rnd.randrange(5) for c in changes}
    for name, key in [("learned_logreg_random5fold", lambda c: fold_of[c["id"]]),
                      ("learned_logreg_leave_one_file_out", lambda c: c["file"])]:
        t = time.perf_counter()
        sel = learned_selector(changes, facts, key)
        selections[name] = sel
        per_change[name] = {"seconds": time.perf_counter() - t,
                            "scores": {c["id"]: score(sel[c["id"]], c["failing"]) for c in changes}}

    # Seed sensitivity of the learned selector (fold assignment only).
    seed_runs = []
    for seed in range(5):
        r2 = random.Random(seed)
        folds = {c["id"]: r2.randrange(5) for c in changes}
        sel = learned_selector(changes, facts, lambda c: folds[c["id"]], seed=seed)
        sc = {c["id"]: score(sel[c["id"]], c["failing"]) for c in changes}
        s_ = summarise("seed", sc, changes)
        seed_runs.append({"seed": seed, "fraction": s_["mean_fraction_selected"], "detected": s_["faulty_changes_detected"],
                          "safe": s_["faulty_changes_fully_safe"], "recall": s_["failing_test_recall"]})

    summaries = [summarise(n, per_change[n]["scores"], changes) | {"selection_seconds": per_change[n]["seconds"]}
                 for n in selections]

    # Adversarial cases named explicitly so the reader can inspect them.
    def pick(pred):
        return [c["id"] for c in changes if pred(c)]
    adversarial = {
        "shared_helper_change_breaks_downstream": pick(lambda c: c["file"] == "units.h" and c["failing"]),
        "function_pointer_only_path": pick(lambda c: c["entity"]["name"] in ("encode_age", "encode_status") and c["failing"]),
        "non_executable_constant_change": pick(lambda c: c["entity"]["kind"] == "global" and c["failing"]),
        "changes_no_test_detects": pick(lambda c: not c["failing"]),
    }
    out = {
        "schema": 1,
        "source_sha256": source_digest(),
        "generated_mutants": len(all_mutants),
        "compilable_changes": len(changes),
        "non_compiling_discarded": len(all_mutants) - len(changes),
        "faulty_changes": sum(1 for c in changes if c["failing"]),
        "undetected_by_full_suite": sum(1 for c in changes if not c["failing"]),
        "tests": len(TESTS),
        "dependency_facts": {k: facts[k] for k in ["call_graph", "constant_uses", "test_entries", "coverage", "function_spans", "header_constants", "timing_seconds"]},
        "summaries": summaries,
        "adversarial_sets": adversarial,
        "learned_seed_sensitivity": seed_runs,
        "changes": [{k: c[k] for k in ["id", "file", "line", "operator", "before", "after", "failing", "entity", "crashed", "crashed_tests"]}
                    | {"selected": {n: sorted(selections[n][c["id"]]) for n in selections}} for c in changes],
        "learned_features": FEATURE_NAMES,
        "seconds_total": time.perf_counter() - t0,
        "limits": [
            "Changes are generated single-token mutants of an authored 6-file fixture, not real commit history.",
            "Safety is relative to this regression suite (standard RTS definition): a technique cannot be safer than retest-all.",
            "Learned selector is trained on ~56 synthetic changes per fold (70 total); Facebook-scale results do not transfer.",
            "Coverage is function-granular, collected once on the unchanged version (as in dynamic RTS).",
        ],
    }
    write_json(RESULTS / "rts.json", out)
    to_sqlite(RESULTS / "impact.db", facts, evaluated, selections, summaries)
    print(json.dumps({s["technique"]: [round(s["mean_fraction_selected"], 3), s["faulty_changes_detected"],
                                       s["faulty_changes_fully_safe"], s["faulty_changes"]] for s in summaries}, indent=1))
    print("changes", len(changes), "faulty", out["faulty_changes"], "seconds", round(out["seconds_total"], 1))


if __name__ == "__main__":
    main()
