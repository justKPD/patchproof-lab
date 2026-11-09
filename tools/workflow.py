"""Execute review tools. Never self-approve a patch."""
import argparse,json,subprocess,sys,time
from build import ROOT
p=argparse.ArgumentParser();p.add_argument("--generate",action="store_true");p.add_argument("--stale-control",action="store_true");a=p.parse_args();stages=[]
def run(name,args):
    t=time.perf_counter();r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=300)
    stages.append({"tool":name,"returncode":r.returncode,"seconds":time.perf_counter()-t,"stdout":r.stdout[-3000:],"stderr":r.stderr[-3000:]})
    if r.returncode:raise RuntimeError(name+" failed")
try:
    run("compile_and_static_analysis",[sys.executable,"tools/build.py"])
    if a.generate:run("context_and_author",[sys.executable,"tools/provider.py","--name","agent-obsolete" if a.stale_control else "agent-current",*(["--stale"] if a.stale_control else [])])
    run("package_provenance",[sys.executable,"tools/package_evidence.py"])
    run("independent_referee",[sys.executable,"tools/evaluate.py"])
    run("regressions",["node","--test","tests/test_engine.mjs"])
    status="AWAITING_HUMAN_REVIEW"
except Exception as exc:status="FAILED";stages.append({"error":str(exc)})
(ROOT/"results/workflow.json").write_text(json.dumps({"status":status,"stages":stages,"authority":"Human review required; no production change is approved."},indent=2),encoding="utf8")
print(status);sys.exit(0 if status=="AWAITING_HUMAN_REVIEW" else 1)

