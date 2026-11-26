"""Reproduce every impact-lab result from source in one command:  python impact/run_all.py"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = [
    ("regression test selection experiment", ["lab/experiment_rts.py"]),
    ("test adequacy experiment", ["lab/adequacy.py"]),
    ("LLM adapter status", ["assistant/llm_assistant.py"]),
    ("assistant evaluation", ["assistant/evaluate_assistant.py"]),
    ("export demo data", ["lab/export_site.py"]),
]
for title, args in STEPS:
    t = time.perf_counter()
    r = subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]], cwd=HERE)
    ok = r.returncode == 0 or (args[0].endswith("llm_assistant.py") and r.returncode == 2)
    print(f"[{'ok' if ok else 'FAILED'}] {title} ({time.perf_counter() - t:.1f}s)")
    if not ok:
        sys.exit(1)
