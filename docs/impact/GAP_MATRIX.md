# Gap matrix: Part 1 (main) vs Part 2 (dev/impact-lab)

| Problem | Part 1 state (main, verified at commit 0d882b9) | Part 2 (this branch) | Evidence | Remaining gap |
|---|---|---|---|---|
| Dependency discovery | Dependencies **declared by hand** in a manifest; README states unseen dependencies are not discovered | Discovered from LLVM IR, Clang AST and per-test llvm-cov profiles | `rts.json` → `dependency_facts`; `tests/test_impact.py::Discovery` | Function granularity only; no cross-language or build-system edges |
| Downstream regressions | Single 41-line function; nothing downstream to break | 6-file system with shared helper and dispatch table; failures measured across components | SQL query 3; 25/59 faulty changes unsafe under a per-file manifest | Small authored system, not real commit history |
| Regression test selection | Declared-manifest rerun vs full rerun, one omitted-dependency control | 8 techniques on 70 generated changes with retest-all ground truth | `technique_summary` table | No timing/cost model beyond test counts |
| Tests beyond expected cases | 6 hand-written mutants, 1 random generator, 27 explicit probes | Mutation analysis over generated changes; 7 strategies at matched budgets, 5 seeds | `adequacy.json` → `strategies` | Requirements-derived BVA cannot find unspecified conditions |
| Turning gaps into tests | — | Every surviving change triaged into a concrete suggested input or marked equivalent | `suite_survivor_suggestions` | Suggestions are not auto-committed as tests |
| Unexpected inputs | Integer bounds and 500-row cap on custom traces | Plus malformed-input cases for the assistant (None, empty, 18k chars, SQL-like, non-English) | `robustness` category | No coverage-guided fuzzing (e.g. libFuzzer) yet |
| AI-assistant evaluation | Optional free-model code author; provider calls failed/rate-limited (recorded) | Structured-output eval harness, 39 cases, 9 categories, validated on 8 faulty variants | `assistant_eval.json` | No real LLM evaluated; no human-labelled cases; single case author |
| Crash isolation | WASM sandbox for generated code | Per-test process re-run when a test crashes | `crashed_tests` in `rts.json` | — |
| Reproducibility | CI builds and runs Part 1 | CI also runs Part 2 and compares fresh outcomes with committed ones | `impact/lab/compare_results.py` | CI on GitHub not yet observed for this branch |
| Data/reporting | JSON evidence | Same, plus SQLite (`impact.db`) and SQL reports | `impact/queries.sql` | — |
| Framing | README/site framed as a Bosch Rexroth work sample | Visible site text neutral; Part 1 evidence files unchanged (hash-pinned) | `site/index.html` | `results/evaluation.json` and `src/controller.cpp` still mention Bosch (unchanged to keep hashes valid) |
