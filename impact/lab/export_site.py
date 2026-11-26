"""Copy the measured results the public page needs into site/impact-data.json (no recomputation)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, RESULTS, write_json  # noqa: E402

rts = json.loads((RESULTS / "rts.json").read_text())
ade = json.loads((RESULTS / "adequacy.json").read_text())
ase = json.loads((RESULTS / "assistant_eval.json").read_text())
facts = rts["dependency_facts"]
write_json(ROOT / "site" / "impact-data.json", {
    "source_sha256": rts["source_sha256"],
    "rts": {k: rts[k] for k in ["generated_mutants", "compilable_changes", "faulty_changes", "undetected_by_full_suite",
                                "tests", "summaries", "learned_seed_sensitivity", "limits"]},
    "graph": {"direct": facts["call_graph"]["direct"], "address_taken": facts["call_graph"]["address_taken"],
              "indirect_callers": facts["call_graph"]["indirect_callers"], "spans": facts["function_spans"],
              "test_entries": facts["test_entries"], "coverage": facts["coverage"]},
    "changes": [{k: c[k] for k in ["id", "file", "line", "operator", "before", "after", "failing", "entity", "selected"]}
                for c in rts["changes"]],
    "adequacy": {k: ade[k] for k in ["budget_calls", "seeds", "live_mutants", "probable_equivalent", "strategies",
                                     "suite_survivor_suggestions", "limits"]},
    "assistant": {k: ase[k] for k in ["cases", "categories", "assistants", "variants_detected", "variants_total",
                                      "detecting_categories", "llm_backed_run", "limits"]},
})
print("site/impact-data.json written")
