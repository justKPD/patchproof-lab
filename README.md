# PatchProof Lab
Independent work sample for Bosch Rexroth internship REF297705V.

Engineering question: Can a generated patch pass its own checks while violating a separately stated requirement, and which evidence needs to run again after a context change?

Live: https://patchproof-lab.vercel.app/
Role: https://jobs.smartrecruiters.com/BoschGroup/744000153500999

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
Execution is portable wasm32, not QNX or embedded Linux target validation. Inputs model integer sensor-command checks, not physical dynamics. No Bosch code, proprietary architecture, controller hardware, MISRA compliance or safety certification is claimed.

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

Mohamed Amin Hamdad is the exact vacancy contact. ORC2 remains an adjacent product-family hypothesis, not a confirmed internship assignment.

