# Architecture comparison and decisions

## A. How to decide which tests to rerun

| Option | Needs | Safe? (measured) | Cost (measured) | Fails when | Decision |
|---|---|---|---|---|---|
| Retest all | nothing | yes | 100% | suite becomes too slow | baseline only |
| Hand-declared manifest | discipline | no (34/59) | 20% | anything transitive or shared | rejected |
| Build/target graph | build system metadata | usually, coarse | high | target granularity is coarse | not applicable to a 1-library fixture |
| Static call graph (direct) | compiler IR | no (50/59) | 36% | function pointers, virtual calls, callbacks | component of hybrid |
| Static + pointer over-approximation | IR | yes (59/59) | 38% | over-selects in pointer-heavy code | fallback inside hybrid |
| Dynamic per-test coverage | instrumented run per test | no (55/59) | 34% | constants, config, data files, new code paths | component of hybrid |
| **Hybrid** | both | **yes (59/59)** | **35%** | stale coverage after large refactors; non-code inputs not modelled | **chosen** |
| Learned (predictive) | large history | no (47–52/59) | 28–32% | small/synthetic history; distribution shift | studied, not chosen |

Why hybrid and not learned: deterministic sources gave full safety at similar cost; the learned model needs
real history to be useful and still gives only statistical guarantees. A learned model becomes attractive
when precise analysis is impossible (very large multi-language codebases) — that is a scale question, not
something this fixture can show.

Data flow:
```
src (C++) ──clang -emit-llvm──► call graph ─┐
          ──clang -ast-dump=json──► def-use ─┤
          ──instrumented .so + 1 profile/test──► coverage ─┤──► select(change) ──► tests to rerun
tests (Python) ──ast──► entry points ───────┘
change (file:line) ──coverage-mapping spans──► changed function | constant
```

## B. Where extra test inputs come from

| Option | Oracle needed | Measured (score) | Decision |
|---|---|---|---|
| Nominal examples | yes | 47% (4 calls) | keep as smoke tests |
| Uniform random | yes | 49% (200) | rejected as the main source |
| Operating-region random | yes | 84% (200) | keep: represents real usage |
| Boundary-value analysis | yes | 100% (53) | keep: cheapest high-yield |
| Property-based, relational generators | no | 67% (200) | keep where no oracle exists |
| Mutation analysis on changed code | — | turns survivors into test goals | keep in review, scoped to changed lines |

## C. How to evaluate an AI assistant

| Option | Strength | Weakness | Used here |
|---|---|---|---|
| Exact checks on structured output (sets, ids, flags) | deterministic, cheap, explainable | needs a structured interface | **primary** |
| LLM-as-judge metrics (e.g. RAGAS faithfulness) | scales to free text | judge is itself unvalidated; cost; variance | not used; would be checked the same way (known-bad answers) |
| Metamorphic groups (paraphrase → same answer) | no oracle needed | only checks consistency | used |
| Adversarial corpus (obsolete + poisoned docs) | tests real failure modes (OWASP LLM01, LLM09) | authored attacks only | used |
| Human review | ground truth for open answers | slow, needs rubric | out of scope; recommended for free-text answers |
| Repeats for non-determinism | detects flakiness | multiplies cost | supported (`--repeats`) |

Validation rule adopted: an evaluation category earns its place only if it catches at least one known-faulty
assistant that the others miss, or covers a stated risk. Currently 8/8 variants caught; metamorphic and
robustness categories are each the sole detector of one variant.
