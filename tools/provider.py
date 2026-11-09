"""Optional free OpenRouter generation, with real compile/test records.
Generated C++ is compiled only to capability-free WASM and executed with a timeout.
No generated source is executed natively. No paid model is accepted.
"""
import argparse,hashlib,json,os,re,sys,time,urllib.request
from pathlib import Path
from build import ROOT,compile_source
from evaluate import BASE,execute,oracle
from context import retrieve
def key():
    value=os.environ.get("OPENROUTER_API_KEY")
    if value:return value
    try:
        import keyring
        return keyring.get_password("trillion-agent","openrouter_api_key") or ""
    except Exception:return ""
def validate_source(source):
    if not isinstance(source,str) or len(source)>16000:raise ValueError("Source size/type")
    if "#" in source or re.search(r'\b(asm|__asm__|__asm|import|include|system|fopen)\b',source):raise ValueError("Unsupported source construct")
    if 'reason(' not in source or 'command(' not in source:raise ValueError("Required ABI")
def generate(name="agent-current",stale=False):
    model=os.environ.get("OPENROUTER_MODEL","cohere/north-mini-code:free")
    if model!="openrouter/free" and not model.endswith(":free"):raise ValueError("Only free models allowed")
    token=key()
    if not token:return {"status":"BLOCKED_NO_KEY"}
    req=json.loads((ROOT/"requirements.json").read_text())
    contract=[x["text"] for x in req["requirements"]]
    if stale:contract=[t.replace("age < timeout_ms. Equality is expired.","age <= timeout_ms. Equality is accepted.") for t in contract]
    context={"id":"obsolete-v0" if stale else "req-v1","requirements":contract,"parameters":["now","stamp","seq","last","valid","enabled","requested","limit","timeout"],"reason_bits":{"invalid":1,"disabled":2,"future":4,"expired":8,"sequence":16},"integer_bounds":req["bounds"]}
    context['retrieval']=retrieve('sensor freshness sequence limit',context['id'],allow_obsolete=stale)
    # Only nominal examples are available to the author. Independent evaluation is performed later.
    nominal=[{**BASE,"id":"nominal-"+str(i),"requested":q} for i,q in enumerate([0,10,50,80])]
    prompt='Implement two C++ functions, both extern "C": int reason(int now,int stamp,int seq,int last,int valid,int enabled,int requested,int limit,int timeout) and int command(same parameters). reason returns ORed failure bits. command returns zero on any failure, otherwise clamped request. No includes, preprocessor, libraries, global state, assembly, imports, or main. Cast unused parameters to void. Return JSON {"source":"complete C++ source", "tests":[{"id":"t1","now":1000,"stamp":990,"seq":2,"last":1,"valid":1,"enabled":1,"requested":50,"limit":80,"timeout":100,"expected_reason":0,"expected_command":50}]}. Write 4 to 12 of your own tests, including edges. A missing requirement must not be invented. Keep analysis short and output source and tests.'
    messages=[{"role":"system","content":prompt},{"role":"user","content":json.dumps({"ticket":"Implement bounded sensor-command validation","context":context,"nominal_examples":nominal})}]
    attempts=[]
    for attempt in range(2):
        payload={"model":model,"temperature":0,"max_tokens":12000,"messages":messages,"reasoning":{"effort":"low","exclude":True}}
        request=urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",data=json.dumps(payload).encode(),headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
        t=time.perf_counter()
        try:
            with urllib.request.urlopen(request,timeout=80) as response:out=json.load(response)
            raw=out["choices"][0]["message"]["content"]
            if not isinstance(raw,str) or not raw.strip():
                attempts.append({"attempt":attempt,"error":"EMPTY_CONTENT","model":out.get("model"),"usage":out.get("usage"),"finish_reason":out["choices"][0].get("finish_reason"),"message_keys":list(out["choices"][0]["message"])})
                messages.append({"role":"user","content":"Return the requested JSON source now. No reasoning text."})
                continue
            obj=json.loads(raw[raw.find("{"):raw.rfind("}")+1]);source=obj["source"];validate_source(source)
            folder=ROOT/"generated"/name;folder.mkdir(parents=True,exist_ok=True)
            src=folder/f"attempt-{attempt}.cpp";src.write_text(source,encoding="utf8")
            dst=ROOT/"site/wasm"/f"{name}.wasm";build=compile_source(src,dst)
            checks=execute(dst,nominal)["results"] if build["ok"] else []
            nominal_ok=build["ok"] and all(all(o[k]==oracle(c)[k] for k in ["reason","command"]) for c,o in zip(nominal,checks))
            record={"attempt":attempt,"model":out.get("model"),"usage":out.get("usage"),"provider_seconds":time.perf_counter()-t,"build":build,"nominal_pass":nominal_ok,"observations":checks,"source":str(src.relative_to(ROOT)).replace("\\","/")}
            attempts.append(record)
            if nominal_ok:
                own=obj.get('tests',[])
                if not isinstance(own,list) or not 4<=len(own)<=12:raise ValueError('Missing author tests')
                for t in own:
                    for field,(low,high) in req['bounds'].items():
                        if type(t.get(field)) is not int or not low<=t[field]<=high:raise ValueError('Author test outside bounds')
                    if type(t.get('expected_reason')) is not int or type(t.get('expected_command')) is not int:raise ValueError('Author expected result missing')
                own_results=execute(dst,own)['results']
                own_pass=all(o['reason']==c['expected_reason'] and o['command']==c['expected_command'] for c,o in zip(own,own_results))
                result={"status":"COMPILED","id":name,"origin":"live-free-model","context":context,"context_sha256":hashlib.sha256(json.dumps(context,sort_keys=True).encode()).hexdigest(),"module":f"wasm/{name}.wasm","attempts":attempts,"source":record["source"],"author_tests":own,"author_test_results":own_results,"author_tests_pass":own_pass,"scope":"One actual provider task; separate evaluation never sent to author."}
                (ROOT/"results"/f"{name}.json").write_text(json.dumps(result,indent=2),encoding="utf8")
                return result
            diagnostics=build["diagnostics"] if not build["ok"] else "Nominal examples did not match contract"
            messages.extend([{"role":"assistant","content":raw},{"role":"user","content":"Repair within the same contract. Tool evidence: "+diagnostics[:3500]}])
        except Exception as exc:
            attempts.append({"attempt":attempt,"error":type(exc).__name__,"message":str(exc)[:250],"provider_seconds":time.perf_counter()-t})
            break
    result={"status":"FAILED","id":name,"context":context,"attempts":attempts}
    (ROOT/"results"/f"{name}.json").write_text(json.dumps(result,indent=2),encoding="utf8")
    return result
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--name",default="agent-current");p.add_argument("--stale",action="store_true");a=p.parse_args()
    result=generate(a.name,a.stale)
    print(json.dumps({"id":a.name,"status":result["status"],"attempts":len(result.get("attempts",[]))}))
    sys.exit(0 if result['status']=='COMPILED' else 2)

