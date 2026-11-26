"""Compare measured outcomes (not timings) of a fresh run with a saved copy. Exit 1 on any difference."""
import json
import sys
from pathlib import Path


def key(path):
    d = json.loads(Path(path).read_text())
    if "summaries" in d:
        return {"summaries": [{k: v for k, v in s.items() if k != "selection_seconds"} for s in d["summaries"]],
                "changes": [(c["id"], c["failing"], c["selected"]) for c in d["changes"]]}
    if "strategies" in d:
        return {"strategies": d["strategies"], "suggestions": d["suite_survivor_suggestions"]}
    return {"assistants": d["assistants"]}


old, new = Path(sys.argv[1]), Path(sys.argv[2])
bad = [f for f in ["rts.json", "adequacy.json", "assistant_eval.json"] if key(old / f) != key(new / f)]
print("identical outcomes" if not bad else f"DIFFERENT: {bad}")
sys.exit(1 if bad else 0)
