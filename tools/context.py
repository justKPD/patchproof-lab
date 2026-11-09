"""Lexical retrieval with explicit revision authority and content hashes."""
import hashlib,json,re,math
from build import ROOT
def retrieve(query,revision="req-v1",allow_obsolete=False):
    if not isinstance(revision,str) or not revision:raise ValueError("A comparison contract revision is required")
    kb=json.loads((ROOT/"context/knowledge.json").read_text())
    tokens=set(re.findall(r"[a-z0-9]+",query.lower()))
    rows=[]
    for doc in kb["documents"]:
        if "revision" not in doc or "authority" not in doc:raise ValueError("Context metadata missing")
        words=re.findall(r"[a-z0-9]+",doc["text"].lower())
        score=sum(words.count(t) for t in tokens)/math.sqrt(max(1,len(words)))
        applicable=doc["authority"]=="current" and doc["revision"] in [revision,"arch-v1"]
        if allow_obsolete:applicable=doc["revision"] in [revision,"arch-v1"]
        if not applicable:continue
        rows.append({**doc,"score":score,"sha256":hashlib.sha256(doc["text"].encode()).hexdigest()})
    rows.sort(key=lambda d:(-d["score"],d["id"]))
    if not rows or not any(d["revision"]==revision for d in rows):raise ValueError("Requested authoritative revision unavailable")
    return {"query":query,"revision":revision,"passages":rows[:3],"method":"Lexical term scoring followed by explicit authority/revision filtering; no vector or semantic search claim."}
if __name__=="__main__":print(json.dumps(retrieve("sensor freshness sequence limit"),indent=2))

