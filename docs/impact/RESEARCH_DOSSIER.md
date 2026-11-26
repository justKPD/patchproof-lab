# Research dossier: testing beyond the passing cases

Scope: the testing problems an R&D engineer typically names when asked *"how do you decide which additional
cases are worth testing when the expected cases already pass?"*, plus the target role's focus on a testing
strategy for an internal AI assistant. For each problem: established methods, existing tools, what was
implemented here, and what the measurements say. Measured numbers come from `impact/results/*.json`
(reproduce with `python impact/run_all.py`).

## Problems studied

| # | Problem | Implemented here |
|---|---------|------------------|
| P1 | Edge cases and boundary conditions | Requirements-based boundary-value analysis, property-based testing, mutation analysis |
| P2 | Unexpected / malformed inputs | Robustness cases for the assistant; bounded input validation (Part 1) |
| P3 | Side effects of a change on existing functionality | Regression test selection (RTS) with retest-all ground truth |
| P4 | Impact analysis: affected components, dependencies, what breaks elsewhere | Dependency discovery from compiler artefacts (IR call graph, AST def-use, per-test coverage) |
| P5 | Real-world usage and failure conditions not in the initial requirements | Operating-region random testing, metamorphic relations; limits documented |
| P6 | Regression testing in complex systems | Technique comparison incl. a learned (predictive) selector |
| P7 | A credible evaluation framework for an AI assistant | Structured-output evaluation harness validated against known-faulty assistants |

---

## P3 / P4 / P6 — Which tests must rerun after a change, and what can break elsewhere?

**Established methods**
* *Retest-all* — the safe but expensive baseline.
* *Regression test selection (RTS)*: rerun only tests affected by the change. A technique is **safe** if it
  selects every test whose outcome can change. Dynamic RTS such as Ekstazi (Gligoric, Eloussi, Marinov,
  ISSTA 2015) records each test's dependencies while it runs; static RTS derives them from a dependency graph
  without running tests (Legunsen et al., FSE 2016 compare both).
* *Build/dependency-graph selection*: run tests that transitively depend on modified targets (the common
  monorepo approach; described as over-selecting in Facebook's predictive-test-selection work).
* *Predictive (learned) test selection*: Machalica et al. (ICSE-SEIP 2019) train a model on historical
  change/test outcomes; Facebook reports roughly halving test infrastructure cost while still reporting over
  95% of individual test failures and over 99.9% of faulty changes. This requires a large history.

**Implemented** (`impact/lab/`): a 6-file C++ system (sensor → limiter → rate limiter → pipeline, a shared
helper header, a config header, and telemetry reached through a function-pointer table). Its 22-test suite is
written like a component owner would write it. Dependencies are *discovered*, not declared:

| Source | Tool | Sees | Misses |
|---|---|---|---|
| Direct call graph | `clang++ -S -emit-llvm`, parsed | transitive direct calls | function-pointer calls |
| + function-pointer edges | address-taken globals + indirect call sites in IR | dispatch tables (conservatively) | nothing here; over-approximates in general |
| Per-test dynamic coverage | `-fprofile-instr-generate`, `llvm-cov export`, one profile per test | everything executed, incl. pointers | non-executable entities (constants) |
| Constant def-use | `clang -Xclang -ast-dump=json` | which functions read a header constant | — |
| Hand-declared manifest | developer-written | the test's own component | transitive and shared-header deps |

Changes are 70 compilable single-token mutants across all 7 files (ROR, AOR, CRP, LCR, BOR, SDL, NEG operators);
for each, the full suite runs to obtain ground truth. 59 of 70 break at least one test.

**Measured** (identical changes for every technique):

| Technique | Tests rerun (mean) | Faulty changes detected | Fully safe |
|---|---|---|---|
| Retest all | 100% | 59/59 | 59/59 |
| Hand-declared manifest | 20% | 51/59 | 34/59 |
| Static call graph (direct) | 36% | 51/59 | 50/59 |
| Static + function pointers | 38% | 59/59 | 59/59 |
| Dynamic per-test coverage | 34% | 55/59 | 55/59 |
| **Hybrid** (coverage + def-use + static fallback) | **35%** | **59/59** | **59/59** |
| Learned, logistic regression (5-fold, 5 seeds) | 31–32% | 53–55/59 | 49–52/59 |
| Learned, leave-one-file-out | 28% | 53/59 | 47/59 |

Findings:
1. **Downstream regressions are real even in 6 files.** A change to the shared `clamp_int` helper fails tests in
   three other components (limiter, rate, pipeline); a change to `age_ms` fails sensor, pipeline and telemetry
   tests (SQL query 3 in `impact/queries.sql`). A per-component manifest is unsafe on 25 of 59 faulty changes.
2. **Each discovery source has a characteristic blind spot**, and each was triggered: direct-call graphs miss
   the dispatch table (6 changes); dynamic coverage misses header-constant changes because constants have no
   executable region (4 changes). Combining sources closes both at ~35% cost.
3. **Crash isolation matters for ground truth.** Three mutants make one test segfault; run in one process this
   was first recorded as "all 22 tests fail". Ground truth now re-runs each test in its own process.
4. **The learned selector did not beat deterministic analysis here**, and was never fully safe. With ~56
   synthetic training changes per fold this is expected; the method's reported benefits rely on large real
   histories and a codebase where precise static/dynamic analysis is impractical.

## P1 / P5 — Which extra inputs are worth running?

**Established methods**
* *Equivalence partitioning and boundary-value analysis* (black-box, from the specification).
* *Random / operational-profile testing*: inputs drawn from the realistic operating region.
* *Property-based testing* (e.g. Hypothesis): generators plus properties that must always hold.
* *Metamorphic testing*: relations between outputs of related inputs; addresses the oracle problem and is
  increasingly applied to LLMs (Cho, Ruberto, Terragni, arXiv:2511.02108).
* *Mutation analysis* to judge test-suite adequacy. Google surfaces surviving mutants on changed lines
  during code review as concrete test goals (Petrović & Ivanković, ICSE-SEIP 2018; Petrović et al., TSE 2021).

**Implemented** (`impact/lab/adequacy.py`): all strategies attack the same 38 non-equivalent pipeline mutants
(51 compiled, 13 found equivalent by a 50k-input search), at matched call budgets, 5 seeds where random.

| Strategy | Calls | Oracle | Mutation score |
|---|---|---|---|
| Nominal examples | 4 | reference | 47% |
| Uniform random | 200 | reference | 49% ± 15% |
| Random in operating region | 200 | reference | 84% ± 3% |
| Boundary-value analysis | 53 | reference | 100% |
| BVA + operating-region random | 200 | reference | 100% |
| Property-based, uniform generators | 200 | none | 42% ± 21% |
| Property-based, relational generators | 200 | none | 67% ± 9% |

Findings:
1. **Where inputs come from matters more than how many.** 4 nominal cases ≈ 200 uniform random cases. Uniform
   integers almost never produce `stamp == now` or `age == timeout`.
2. **Property-based testing is only as good as its generator.** The same properties went from 42% to 67% when the
   generator encoded relationships (age relative to timeout, sequence relative to last).
3. **Oracle-free checks are weaker but available.** For an AI assistant there often is no exact oracle; the
   property/metamorphic rows are the relevant comparison there.
4. **Surviving mutants become concrete tests.** All 11 changes the team's suite missed were triaged: 2 are
   killable at the pipeline (e.g. `stamp > now` → `stamp >= now` is exposed by `stamp == now`), 6 only at a unit
   ABI (4 because the sensor tests assert `flags & bit` instead of exact equality, 2 in telemetry), 3 are equivalent.

Caveat: BVA's 100% is partly a property of this fixture, where every code condition corresponds to a written
requirement. Conditions *not* in the requirements (problem P5) are exactly what requirements-based BVA cannot
find; operating-region random and code-derived boundaries are the complements.

## P2 / P7 — Evaluating an internal AI assistant

**Established approaches**
* *Reference-free LLM metrics* such as RAGAS (Es et al., arXiv:2309.15217): faithfulness, answer relevance,
  context precision/recall — usually computed with an LLM as judge.
* *Security test categories* from the OWASP Top 10 for LLM Applications 2025 (LLM01 prompt injection,
  LLM02 sensitive information disclosure, LLM06 excessive agency, LLM09 misinformation, …).
* *Metamorphic testing* for robustness to paraphrase.

**Implemented** (`impact/assistant/`): a test-impact assistant with structured output
(`answer, tests, citations, abstained`) over this repository's requirements and discovered dependencies,
with one obsolete and one poisoned document in the corpus on purpose. 39 cases in 9 categories:
requirement facts, stale context, downstream impact (ground truth = tests that actually failed on generated
changes), metamorphic paraphrase groups, abstention, indirect prompt injection, authority over-claims,
citation integrity, malformed input.

**Validating the evaluation**: 8 assistant variants each inject one known failure. All 8 are caught; two are
caught by exactly one category (paraphrase brittleness only by the metamorphic group, input crashes only by
the robustness cases), which is evidence for keeping both. During development the harness found 4 real
defects in the reference assistant itself (stopwords matching requirement text, missing def-use facts causing
a crash on `config.h`, no stemming of "freshness"); these were fixed and are now regression cases.

An LLM-backed assistant with the same interface is included (`llm_assistant.py`); its plumbing is tested
against a local stub, but **no LLM result is claimed** because no model credentials were available.

## Sources
* Gligoric, Eloussi, Marinov. *Practical Regression Test Selection with Dynamic File Dependencies.* ISSTA 2015.
* Legunsen et al. *An Extensive Study of Static Regression Test Selection in Modern Software Evolution.* FSE 2016.
* Machalica, Samylkin, Porth, Chandra. *Predictive Test Selection.* ICSE-SEIP 2019, arXiv:1810.05286.
* Petrović, Ivanković. *State of Mutation Testing at Google.* ICSE-SEIP 2018; Petrović et al. *Practical Mutation Testing at Scale*, TSE 2021 (arXiv:2102.11378).
* Es et al. *RAGAS: Automated Evaluation of Retrieval Augmented Generation.* arXiv:2309.15217.
* OWASP Top 10 for LLM Applications 2025.
* Cho, Ruberto, Terragni. *Metamorphic Testing of Large Language Models for NLP.* arXiv:2511.02108.
