# PatchProof Lab
Independent software-testing work sample by Drona Koppula Putta. Authored fixture code only; no employer code, data or architecture.

Engineering questions:
1. Can a patch pass its own checks while violating a separately stated requirement? (Part 1)
2. When the expected tests pass, which other tests must rerun after a change, which extra inputs are worth running, and how do you evaluate an AI assistant credibly? (Part 2, `impact/`)

Live: https://patchproof-lab.vercel.app/ (Part 2 page: `/impact.html` once deployed from this branch)

## Part 2: change impact and assistant evaluation (`impact/`)
Three measured experiments on a 6-file C++ system (shared helper header, config header, function-pointer dispatch):

* **Which tests must rerun?** Dependencies are discovered from LLVM IR (call graph), the Clang AST (constant def-use) and one llvm-cov profile per test. On 70 generated changes with retest-all ground truth, a hand-declared manifest is unsafe on 25/59 faulty changes; the hybrid selector is safe on 59/59 while rerunning 35% of tests. A learned (logistic-regression) selector was not safe on any of 5 seeds.
* **Which extra inputs are worth running?** Seven strategies at matched budgets: 4 nominal cases score 47%, 200 uniform random 49%, 53 boundary-value cases 100% (on this fixture). Every change the team's suite misses is turned into a concrete suggested test or marked equivalent.
* **AI-assistant evaluation.** 39 structured cases in 9 categories (stale context, indirect prompt injection, abstention, citation integrity, metamorphic paraphrase, downstream impact, malformed input, ...). The harness is validated against 8 known-faulty assistants (8/8 caught). An LLM-backed adapter exists; no LLM result is claimed (no credentials).

Reproduce (needs clang++ with libclang-rt profile runtime, llvm-cov, llvm-profdata, Python 3.11+):

    python -m pip install hypothesis scikit-learn
    python impact/run_all.py            # ~30 s; writes impact/results/*.json and impact.db
    python -m unittest discover -s tests
    sqlite3 impact/results/impact.db < impact/queries.sql

Write-ups: `docs/impact/RESEARCH_DOSSIER.md`, `GAP_MATRIX.md`, `ARCHITECTURE_COMPARISON.md`.

## Part 1: patch verification workspace

## What runs
The public workspace loads hash-verified WebAssembly compiled from C++. Visitors select a candidate, change timeout and limits, supply bounded JSON traces, execute, inspect guard/output disagreements, play or scrub the recorded trace and export the exact run. A local command interface invokes these tools without inventing results.

The second workspace executes a declared dependency experiment. It compares scoped reruns with a full rerun and rejects missing identities. The full audit is an additional cost. An omitted dependency is retained as a negative control.

The local workflow optionally calls a free OpenRouter model, compiles its response to capability-free WASM, executes tests with a timeout, runs an independent Python oracle and prepares a human-review record. Generated source never executes natively.

## Reproduce
Python 3.11+, Node 22+, Zig 0.14.1. Selected clang-tidy checks are recorded if available.

    python -m pip install --target .compiler ziglang==0.14.1

Set ZIG_EXE to .compiler/ziglang/zig.exe on Windows or .compiler/ziglang/zig on Linux. Set CLANG_TIDY to your installed analyzer.

    python tools/build.py
    python tools/package_evidence.py
    python tools/evaluate.py
    node --test tests/test_engine.mjs
    python -m unittest discover -s tests
    python -m http.server 8799 --directory site

Review handoff:

    python tools/workflow.py

Optional live generation:

    python tools/workflow.py --generate

Use OPENROUTER_API_KEY in the process environment or the user's existing trillion-agent/openrouter_api_key keyring entry. Never commit credentials. OPENROUTER_MODEL must be openrouter/free or a :free model. Provider failures remain in results. No public LLM endpoint is exposed.

## Evidence boundaries
The reference and six mutants are authored fixtures. Four nominal examples omit important conditions. Evaluation has 187 calls per seed: 27 explicit probes and 160 combined cases. The second seed shares the generator and explicit probes; it is not an external benchmark.

The Python oracle is separately implemented but shares the requirements. Shared specification errors remain possible. The manual reference is not a timed human engineering baseline. No industrial time or cost saving is claimed.

Scoped validation uses an explicit dependency manifest and test-local configuration. It does not discover arbitrary code dependencies. An incorrect manifest can invalidate the conclusion; the negative control demonstrates this.

## Target and safety
Execution is portable wasm32, not QNX or embedded Linux target validation. Inputs model integer sensor-command checks, not physical dynamics. No employer code, proprietary architecture, controller hardware, MISRA compliance or safety certification is claimed.

Selected clang-analyzer and bugprone checks do not establish full MISRA compliance.
QNX access: https://www.qnx.com/developers/docs/qnxeverywhere/introduction.html
Analyzer: https://clang.llvm.org/extra/clang-tidy/

## Files
src/controller.cpp: reference and explicit compile-time mutants.
requirements.json: contract and bounds.
tools/provider.py: bounded free-model author and its tests.
tools/evaluate.py: independent oracle and comparative runs.
tools/workflow.py: actual tools and human-review handoff.
site/: public workspace and compiled artifacts.
results/: actual build and evaluation evidence.

History: Part 1 was first prepared as a work sample for a Bosch Rexroth internship application; its hash-pinned evidence files still contain that wording and are left unchanged so the published hashes stay valid.

