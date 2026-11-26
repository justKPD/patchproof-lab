"""Experiment 2: which additional test inputs are worth running when the expected cases pass?

Strategies are compared by mutation score on the same compiled changes, at matched call budgets,
over several seeds. Two oracle situations are separated because they matter in practice:
  * with a reference oracle (independent Python model of the requirements), and
  * oracle-free (properties / metamorphic relations only) - the situation an AI-assistant tester is often in.
Finally, every change that survives the team's own suite is turned into a concrete suggested test.
"""
from __future__ import annotations

import ctypes
import json
import random
import shutil
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, CPP, RESULTS, compile_library, source_digest, temp_copy_of_sources, write_json  # noqa: E402
from mutate import generate, materialise  # noqa: E402

ARGS = ["now", "stamp", "seq", "last", "valid", "enabled", "requested", "limit", "timeout", "prev", "max_step"]
BOUNDS = {"now": (0, 1_000_000), "stamp": (0, 1_000_000), "seq": (0, 1_000_000), "last": (-1, 1_000_000),
          "valid": (0, 1), "enabled": (0, 1), "requested": (-1000, 1000), "limit": (0, 1000),
          "timeout": (1, 10_000), "prev": (0, 1000), "max_step": (-5, 100)}
NOMINAL = dict(now=1000, stamp=990, seq=2, last=1, valid=1, enabled=1, requested=50, limit=80, timeout=100, prev=40, max_step=25)
DEFAULT_STEP = 25  # requirement R-RATE (independent restatement, not read from config.h)


def oracle(c: dict) -> int:
    """Independent restatement of R-VALID..R-RATE. Shares the specification, not the code."""
    if (not c["valid"] or not c["enabled"] or c["stamp"] > c["now"]
            or c["now"] - c["stamp"] >= c["timeout"] or c["seq"] <= c["last"]):
        return 0
    target = max(0, min(c["limit"], c["requested"]))
    step = c["max_step"] if c["max_step"] > 0 else DEFAULT_STEP
    return c["prev"] + max(-step, min(step, target - c["prev"]))


def reason_oracle(c: dict) -> int:
    return ((0 if c["valid"] else 1) | (0 if c["enabled"] else 2) | (4 if c["stamp"] > c["now"] else 0)
            | (8 if c["now"] - c["stamp"] >= c["timeout"] else 0) | (16 if c["seq"] <= c["last"] else 0))


def telemetry_oracle(kind: int, a: int, b: int) -> int:
    if kind not in (0, 1):
        return -2
    if kind == 0:
        return (a << 16) | (b & 0xFFFF)
    return -1 if a - b < 0 else a - b


# ---------- input generation strategies ----------
def nominal_cases(_budget, _seed):
    return [{**NOMINAL, "requested": q} for q in (0, 10, 50, 80)]


def random_cases(budget, seed):
    rng = random.Random(seed)
    return [{k: rng.randint(*BOUNDS[k]) for k in ARGS} for _ in range(budget)]


def random_near_nominal(budget, seed):
    """Random inputs in the realistic operating region (the common 'smarter random' baseline)."""
    rng = random.Random(seed)
    rows = []
    for _ in range(budget):
        now = rng.randint(500, 2000)
        rows.append(dict(now=now, stamp=now - rng.randint(-20, 200), seq=rng.randint(0, 5), last=rng.randint(-1, 4),
                         valid=rng.randint(0, 1), enabled=rng.randint(0, 1), requested=rng.randint(-50, 150),
                         limit=rng.randint(0, 120), timeout=rng.randint(50, 150), prev=rng.randint(0, 120),
                         max_step=rng.randint(-2, 40)))
    return rows


def boundary_cases(_budget=None, _seed=None):
    """Requirements-based boundary-value analysis: each stated relation probed at x-1, x, x+1
    (one factor at a time around the nominal row), plus domain extremes."""
    n = NOMINAL
    rows = []

    def add(**kw):
        rows.append({**n, **kw})
    for d in (-1, 0, 1):
        add(stamp=n["now"] - n["timeout"] + d)              # R-FRESH: age vs timeout
        add(stamp=n["now"] + d)                             # R-FUTURE: stamp vs now
        add(seq=n["last"] + d)                              # R-ORDER: seq vs last
        add(requested=0 + d, prev=0)                        # R-LIMIT: lower clamp
        add(requested=n["limit"] + d, prev=n["limit"])      # R-LIMIT: upper clamp
        add(requested=100, prev=0, max_step=0 + d)          # R-RATE: default-step selector
        add(requested=80, prev=80 - n["max_step"] + d)      # R-RATE: +step boundary
        add(requested=0, prev=n["max_step"] + d)            # R-RATE: -step boundary
        add(requested=100, prev=0, max_step=DEFAULT_STEP + d)
    for v in (0, 1):
        add(valid=v)                                        # R-VALID
        add(enabled=v)                                      # R-ENABLE
    for k in ARGS:                                          # domain extremes
        lo, hi = BOUNDS[k]
        add(**{k: lo})
        add(**{k: hi})
    return rows


STRATEGIES_WITH_ORACLE = {"nominal_4": nominal_cases, "random_uniform": random_cases,
                          "random_operating_region": random_near_nominal, "boundary_value_analysis": boundary_cases}


# ---------- oracle-free checks ----------
def property_violations(f, c: dict) -> bool:
    """Partial oracles + metamorphic relations. Returns True if any is violated."""
    out = f(c)
    rejected = (not c["valid"] or not c["enabled"] or c["stamp"] > c["now"]
                or c["now"] - c["stamp"] >= c["timeout"] or c["seq"] <= c["last"])
    step = c["max_step"] if c["max_step"] > 0 else DEFAULT_STEP
    if rejected:
        return out != 0                                                   # P1 fail-safe
    if abs(out - c["prev"]) > step:                                       # P2 rate bound
        return True
    target = max(0, min(c["limit"], c["requested"]))
    if not (min(c["prev"], target) <= out <= max(c["prev"], target)):    # P3 moves toward target only
        return True
    if c["requested"] > c["limit"] and f({**c, "requested": c["limit"]}) != out:   # MR1 saturation
        return True
    if c["max_step"] > 0:                                                 # MR2 larger step never slower
        bigger = f({**c, "max_step": c["max_step"] + 1})
        if abs(target - bigger) > abs(target - out):
            return True
    if c["now"] - c["stamp"] > 0 and f({**c, "stamp": c["stamp"] + 1}) != out:     # MR3 fresher sample, same command
        return True
    return False


def hypothesis_kills(f, budget, seed, strategy=None) -> tuple[bool, int, dict | None]:
    from hypothesis import HealthCheck, Phase, given, seed as hseed, settings, strategies as st
    calls = {"n": 0}
    found = {}

    def counted(c):
        calls["n"] += 1
        return f(c)

    @hseed(seed)
    @settings(max_examples=budget, database=None, deadline=None, derandomize=False,
              suppress_health_check=list(HealthCheck), phases=[Phase.generate])
    @given(strategy if strategy is not None else st.fixed_dictionaries({k: st.integers(*BOUNDS[k]) for k in ARGS}))
    def prop(c):
        if property_violations(counted, c):
            found.setdefault("case", c)
            raise AssertionError
    try:
        prop()
        return False, calls["n"], None
    except AssertionError:
        return True, calls["n"], found.get("case")


def structured_inputs():
    """Relational generator: draws ages, sequence gaps and steps relative to each other,
    the way a tester encodes domain structure instead of independent uniform integers."""
    from hypothesis import strategies as st

    @st.composite
    def build(draw):
        timeout = draw(st.integers(1, 10_000))
        now = draw(st.integers(timeout + 50, 1_000_000))
        age = draw(st.integers(-50, timeout + 50))
        last = draw(st.integers(-1, 999_990))
        limit = draw(st.integers(0, 1000))
        return dict(now=now, stamp=now - age, seq=last + draw(st.integers(-3, 3)), last=last,
                    valid=draw(st.integers(0, 1)), enabled=draw(st.integers(0, 1)),
                    requested=draw(st.integers(-1000, 1000)), limit=limit, timeout=timeout,
                    prev=draw(st.integers(0, 1000)), max_step=draw(st.integers(-5, 100)))
    return build()


def hypothesis_structured_kills(f, budget, seed):
    return hypothesis_kills(f, budget, seed, strategy=structured_inputs())


def metamorphic_random_kills(f, budget, seed):
    """Oracle-free baseline without Hypothesis's boundary bias: same properties on uniform random inputs."""
    calls = {"n": 0}

    def counted(c):
        calls["n"] += 1
        return f(c)
    for c in random_cases(budget, seed):
        if property_violations(counted, c):
            return True, calls["n"]
    return False, calls["n"]


# ---------- execution ----------
def load(path: Path):
    lib = ctypes.CDLL(str(path))
    lib.pipeline_step.restype = ctypes.c_int
    return lambda c: lib.pipeline_step(*[int(c[k]) for k in ARGS])


def main(budget=200, seeds=(0, 1, 2, 3, 4)):
    t0 = time.perf_counter()
    keep = BUILD / "adequacy"
    keep.mkdir(parents=True, exist_ok=True)
    ref_info = compile_library(CPP, keep / "reference.so")
    assert ref_info["ok"], ref_info["stderr"]
    ref = load(keep / "reference.so")
    # Sanity: reference must agree with the oracle on every generated input and satisfy all properties.
    for rows in [boundary_cases(), random_cases(2000, 99), random_near_nominal(2000, 99)]:
        bad = [c for c in rows if ref(c) != oracle(c)]
        assert not bad, ("reference disagrees with oracle", bad[:3])
        assert not any(property_violations(ref, c) for c in rows), "reference violates a property"

    mutants = [m for m in generate() if m["file"] != "telemetry.cpp"]   # pipeline contract only
    compiled = []
    for m in mutants:
        d = temp_copy_of_sources()
        materialise(m, d)
        out = keep / f"{m['id']}.so"
        if compile_library(d, out)["ok"]:
            compiled.append((m, load(out)))
        shutil.rmtree(d, ignore_errors=True)

    def kills_with_oracle(f, rows):
        for i, c in enumerate(rows, 1):
            if f(c) != oracle(c):
                return True, i, c
        return False, len(rows), None

    # Probable equivalents: survive a 50k random sweep plus BVA plus all property checks.
    big = random_near_nominal(25_000, 12345) + random_cases(25_000, 54321) + boundary_cases()
    probable_equivalent = {m["id"] for m, f in compiled
                           if not kills_with_oracle(f, big)[0] and not any(property_violations(f, c) for c in big[:5000])}
    live = [(m, f) for m, f in compiled if m["id"] not in probable_equivalent]

    bva_size = len(boundary_cases())
    table = []
    for name, gen in STRATEGIES_WITH_ORACLE.items():
        for b in sorted({budget, bva_size}):
            if name in ("nominal_4", "boundary_value_analysis") and b != budget:
                continue
            per_seed = []
            for s in (seeds if name.startswith("random") else (0,)):
                rows = gen(b, s)
                killed = sum(kills_with_oracle(f, rows)[0] for _, f in live)
                per_seed.append(killed)
            table.append({"strategy": name, "oracle": "reference", "budget_calls": len(gen(b, 0)),
                          "seeds": len(per_seed), "killed_mean": statistics.mean(per_seed),
                          "killed_sd": statistics.pstdev(per_seed), "live_mutants": len(live),
                          "mutation_score_mean": statistics.mean(per_seed) / len(live)})
    # combined: BVA + random_operating_region to the same total budget
    per_seed = []
    for s in seeds:
        rows = boundary_cases() + random_near_nominal(max(0, budget - bva_size), s)
        per_seed.append(sum(kills_with_oracle(f, rows)[0] for _, f in live))
    table.append({"strategy": "bva_plus_operating_region_random", "oracle": "reference", "budget_calls": budget,
                  "seeds": len(seeds), "killed_mean": statistics.mean(per_seed), "killed_sd": statistics.pstdev(per_seed),
                  "live_mutants": len(live), "mutation_score_mean": statistics.mean(per_seed) / len(live)})
    # oracle-free
    for name, fn in [("property_based_hypothesis_uniform", hypothesis_kills),
                     ("property_based_hypothesis_structured", hypothesis_structured_kills),
                     ("properties_on_uniform_random", metamorphic_random_kills)]:
        per_seed, calls = [], []
        for s in seeds:
            k, used = 0, 0
            for _, f in live:
                r = fn(f, budget // 4, s)  # each property check makes up to ~4 calls: budget in calls
                k += r[0]
                used += r[1]
            per_seed.append(k)
            calls.append(used / len(live))
        table.append({"strategy": name, "oracle": "none (properties + metamorphic relations)",
                      "budget_calls": budget, "mean_calls_used_per_mutant": statistics.mean(calls),
                      "seeds": len(seeds), "killed_mean": statistics.mean(per_seed), "killed_sd": statistics.pstdev(per_seed),
                      "live_mutants": len(live), "mutation_score_mean": statistics.mean(per_seed) / len(live)})

    # Which strategy kills which mutant (seed 0) - the per-mutant matrix shown in the demo.
    matrix = []
    for m, f in live:
        row = {"id": m["id"], "file": m["file"], "change": f"{m['before']}  ->  {m['after']}"}
        for name, gen in STRATEGIES_WITH_ORACLE.items():
            row[name] = kills_with_oracle(f, gen(budget, 0))[0]
        row["property_based_hypothesis_uniform"] = hypothesis_kills(f, budget // 4, 0)[0]
        row["property_based_hypothesis_structured"] = hypothesis_structured_kills(f, budget // 4, 0)[0]
        matrix.append(row)

    # Surviving mutants of the TEAM's suite -> concrete suggested tests.
    rts = json.loads((RESULTS / "rts.json").read_text())
    survivors = [c for c in rts["changes"] if not c["failing"]]
    suggestions = []
    by_id = {m["id"]: f for m, f in compiled}
    for c in survivors:
        if c["id"] in probable_equivalent:
            suggestions.append({"change": c["id"], "status": "probably equivalent (no input found in 50k+ calls)",
                                "edit": f"{c['before']}  ->  {c['after']}"})
            continue
        f = by_id.get(c["id"])
        if f is None:
            suggestions.append({"change": c["id"], "status": "outside pipeline contract (telemetry); see telemetry note",
                                "edit": f"{c['before']}  ->  {c['after']}"})
            continue
        killed, _, case = kills_with_oracle(f, boundary_cases())
        source = "boundary_value_analysis"
        if not killed:
            killed, _, case = kills_with_oracle(f, big)
            source = "random sweep"
        suggestions.append({"change": c["id"], "edit": f"{c['before']}  ->  {c['after']}", "status": "killable",
                            "found_by": source, "suggested_test_input": case,
                            "expected_by_requirements": oracle(case), "observed_on_changed_code": f(case)})

    # Unit-level follow-up: survivors that are invisible through pipeline_step may be visible at a unit ABI.
    unit_dir = temp_copy_of_sources()
    for sug in suggestions:
        if sug["status"] == "killable":
            continue
        m = next(x for x in generate() if x["id"] == sug["change"])
        d = temp_copy_of_sources()
        materialise(m, d)
        lib_path = keep / f"unit-{m['id']}.so"
        compile_library(d, lib_path)
        shutil.rmtree(d, ignore_errors=True)
        lib = ctypes.CDLL(str(lib_path))
        hit = None
        if m["file"] == "sensor.cpp":
            for c in boundary_cases():
                got = lib.validate_sample(*[c[k] for k in ["now", "stamp", "seq", "last", "valid", "enabled", "timeout"]])
                if got != reason_oracle(c):
                    hit = {"abi": "validate_sample", "input": {k: c[k] for k in ["now", "stamp", "seq", "last", "valid", "enabled", "timeout"]},
                           "expected_reason_code": reason_oracle(c), "observed_reason_code": got}
                    break
        if m["file"] == "telemetry.cpp":
            for kind, a, b in [(1, 1000, 1000 + d_) for d_ in (-1, 0, 1)] + [(k, 0, 0) for k in (-1, 0, 1, 2)]:
                got = lib.telemetry_dispatch(kind, a, b)
                if got != telemetry_oracle(kind, a, b):
                    hit = {"abi": "telemetry_dispatch", "input": {"kind": kind, "a": a, "b": b},
                           "expected": telemetry_oracle(kind, a, b), "observed": got}
                    break
        if hit:
            sug["status"] = "killable at unit level only (not observable through pipeline_step)"
            sug["suggested_unit_test"] = hit
        elif m["file"] in ("sensor.cpp", "telemetry.cpp"):
            sug["status"] = "probably equivalent at unit level too (boundary probes found no difference)"
    shutil.rmtree(unit_dir, ignore_errors=True)

    out = {"schema": 1, "source_sha256": source_digest(), "budget_calls": budget, "seeds": list(seeds),
           "bva_size": bva_size, "compiled_pipeline_mutants": len(compiled),
           "probable_equivalent": sorted(probable_equivalent), "live_mutants": len(live),
           "strategies": table, "kill_matrix_seed0": matrix, "suite_survivor_suggestions": suggestions,
           "seconds": time.perf_counter() - t0,
           "limits": ["Equivalence is estimated by search, not proven.",
                      "The Python oracle restates the same written requirements; a requirement error is shared.",
                      "Mutants are single-token changes; real faults can be multi-location.",
                      "Property checks embed requirement knowledge (they are partial oracles)."]}
    write_json(RESULTS / "adequacy.json", out)
    for row in table:
        print(f"{row['strategy']:36s} calls={row['budget_calls']:4d} killed={row['killed_mean']:.1f}±{row['killed_sd']:.1f}/{row['live_mutants']} score={row['mutation_score_mean']:.2f}")
    print("probable equivalent:", sorted(probable_equivalent))
    for s in suggestions:
        print(s)
    shutil.rmtree(keep, ignore_errors=True)


if __name__ == "__main__":
    main()
