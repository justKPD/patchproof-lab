import json,shutil
from pathlib import Path
from build import ROOT,sha
build=json.loads((ROOT/'results/build.json').read_text())
for c in build['candidates']:
    c['source_public']='controller.cpp'
    c['command']=[Path(x).name if ':\\' in x or ':/' in x else x for x in c['command']]
for name in ['agent-current','agent-obsolete']:
    p=ROOT/'results'/f'{name}.json'
    if not p.exists():continue
    record=json.loads(p.read_text())
    if record['status']!='COMPILED':continue
    attempt=record['attempts'][-1];dest=ROOT/'site'/f'{name}.cpp'
    shutil.copy2(ROOT/record['source'],dest)
    c={'id':name,'origin':'live-free-model','module':record['module'],'wasm_sha256':sha(ROOT/'site'/record['module']),'source_sha256':sha(dest),'source_public':dest.name,'model':attempt['model'],'context_id':record['context']['id'],'attempts':len(record['attempts']),'provider_seconds':sum(a.get('provider_seconds',0) for a in record['attempts']),'usage':attempt.get('usage'),'build_seconds':attempt['build']['seconds']}
    build['candidates'].append(c)
shutil.copy2(ROOT/'requirements.json',ROOT/'site/requirements.json')
shutil.copy2(ROOT/'src/controller.cpp',ROOT/'site/controller.cpp')
(ROOT/'site/build.json').write_text(json.dumps(build,indent=2),encoding='utf8')
print(json.dumps({'published_candidates':len(build['candidates'])}))
