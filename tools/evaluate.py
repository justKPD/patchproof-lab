"""Independent Python oracle and declared fixture evaluation. Candidate cannot edit this file."""
import hashlib,json,random,subprocess,time
from pathlib import Path
from build import ROOT
KEYS=["now","stamp","seq","last","valid","enabled","requested","limit","timeout"]
BASE=dict(now=1000,stamp=990,seq=2,last=1,valid=1,enabled=1,requested=50,limit=80,timeout=100)
def oracle(c):
    flags=sum([1 if not c["valid"] else 0,2 if not c["enabled"] else 0,4 if c["stamp"]>c["now"] else 0,8 if c["now"]-c["stamp"]>=c["timeout"] else 0,16 if c["seq"]<=c["last"] else 0])
    return {"reason":flags,"command":0 if flags else max(0,min(c["limit"],c["requested"]))}
def cases(seed=42):
    rows=[]
    def add(group,changes,dep):
        c={**BASE,**changes,"id":f"{group}-{len(rows):03d}","requirement":group,"dependencies":dep}
        rows.append(c)
    for q in [0,10,50,80]:add("nominal",{"requested":q},["module"])
    for age in [0,1,98,99,100,101,500]:add("R-FRESH",{"stamp":1000-age},["module","timeout"])
    for lead in [1,10,100]:add("R-FUTURE",{"stamp":1000+lead},["module"])
    for seq in [0,1,2,100]:add("R-ORDER",{"seq":seq},["module"])
    for requested in [-100,-1,0,80,81,100,1000]:add("R-LIMIT",{"requested":requested},["module","limit"])
    add("R-VALID",{"valid":0},["module"]);add("R-ENABLE",{"enabled":0},["module"])
    rng=random.Random(seed)
    for _ in range(160):
        add("combined",{"stamp":1000+rng.randint(-150,30),"seq":rng.randint(0,4),"valid":rng.randint(0,1),"enabled":rng.randint(0,1),"requested":rng.randint(-100,200)},["module"])
    return rows
def execute(module,rows):
    p=subprocess.run(["node",str(ROOT/"tools/wasm_runner.mjs")],input=json.dumps({"module":str(module),"cases":rows}),capture_output=True,text=True,timeout=10)
    if p.returncode:raise RuntimeError(p.stderr)
    return json.loads(p.stdout)
def compare(candidate,rows):
    run=execute(ROOT/"site"/candidate["module"],rows)
    observations=[]
    for c,o in zip(rows,run["results"]):
        e=oracle(c);ok=all(o[k]==e[k] for k in ["reason","command"])
        observations.append({"case":c,"observed":o,"expected":e,"passed":ok})
    return {"id":candidate["id"],"origin":candidate["origin"],"cases":len(rows),"failed":sum(not x["passed"] for x in observations),"passed":all(x["passed"] for x in observations),"execution_ms":run["execution_ms"],"observations":observations}
def context_experiment(rows):
    # Test-local configuration is explicit: only designated probe cases read the changed field.
    base=ROOT/"site/wasm/manual-reference.wasm"
    experiments=[]
    for change,key,value in [("documentation-comment",None,None),("timeout-100-to-60","timeout",60),("limit-80-to-40","limit",40),("module-changed","module",None),("undeclared-dependency-negative-control","timeout",60)]:
        changed=[]
        affected=[]
        for c in rows:
            d=dict(c)
            if key in c["dependencies"]:
                affected.append(c["id"])
                if key!="module":d[key]=value
            if change=="undeclared-dependency-negative-control" and c["id"]=="combined-027":
                d.update(timeout=1,valid=1,enabled=1,seq=2,stamp=990,requested=50)
            changed.append(d)
        active=ROOT/"site/wasm/future-accepted.wasm" if key=="module" else base
        full=execute(active,changed)["results"]
        selected=[c for c in changed if c["id"] in affected]
        rerun=execute(active,selected)["results"] if selected else []
        before=execute(base,rows)["results"]; merged={o["id"]:o for o in before};merged.update({o["id"]:o for o in rerun})
        equal=all(merged[o["id"]]==o for o in full)
        experiments.append({"change":change,"all_cases":len(rows),"full_rerun":len(rows),"whole_context_hash_rerun":len(rows),"dependency_rerun":len(selected),"same_as_full_rerun":equal,"test_calls_saved":len(rows)-len(selected),"scope":"Declared dependency manifest; authored change set; not inferred arbitrary code dependencies."})
    return experiments
def main():
    build=json.loads((ROOT/"site/build.json").read_text())
    results=[]
    for candidate in build["candidates"]:
        r=compare(candidate,cases())
        own=compare(candidate,cases()[:4])
        held=compare(candidate,cases(17))
        r.update(nominal_pass=own["passed"],heldout_seed_failed=held["failed"],heldout_seed_cases=held["cases"])
        results.append(r)
    summary={"schema":1,"oracle_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"fixture":"Authored deterministic sensor-command contract; 160 combined cases plus explicit probes; two seeds share generators and explicit probes.","candidates":results,"context_experiments":context_experiment(cases()),"limits":["Authored mutants are not LLM benchmark results.","No Bosch code, hardware, QNX target, MISRA certification or independent human study.","Dependency manifest is declared; unseen dependencies are not automatically discovered.","Test-call counts are validation effort units, not monetary or wall-time savings.","Manual reference is authored, not a timed human baseline."]}
    (ROOT/"results/evaluation.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    (ROOT/"site/evidence.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    print(json.dumps([{"id":r["id"],"own":r["nominal_pass"],"failed":r["failed"]} for r in results]))
if __name__=="__main__":main()

