import {validateTrace,instantiate,execute,labels,defaultTrace,canonical,hash,planRevalidation} from './engine.mjs';
const $=id=>document.getElementById(id),state={build:null,evidence:null,req:null,run:null,index:0,timer:null,context:null},cache=new Map();
function error(e){$('error').textContent=e.message??String(e);$('error').hidden=false;setTimeout(()=>$('error').hidden=true,8000);}
async function loadModule(id){if(cache.has(id))return cache.get(id);const c=state.build.candidates.find(x=>x.id===id);if(!c)throw Error('Unknown compiled candidate');const bytes=await(await fetch(c.module)).arrayBuffer();const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');if(actual!==c.wasm_sha256)throw Error('Module hash does not match build record');const e=await instantiate(bytes);cache.set(id,e);return e;}
function stop(){clearInterval(state.timer);state.timer=null;$('play').textContent='▶ Play trace';$('system').classList.remove('playing');}
function text(id,v){$(id).textContent=v;}
function show(){
 if(!state.run)return;const row=state.run.observations[state.index],c=row.case,o=row.observed,e=row.expected;
 text('age',(c.now-c.stamp)+' ms');text('observed',o.command);text('expected',e.command);text('case-id',c.id);
 text('svg-age','Age '+(c.now-c.stamp)+' ms');text('svg-seq','Sequence '+c.seq+' / last '+c.last);text('svg-request','Request '+c.requested+' units');
 text('svg-candidate',o.reason?'REJECT':'ACCEPT');text('svg-reference',e.reason?'REJECT':'ACCEPT');
 text('svg-reason',labels(o.reason).join(', ')||'All implemented guards passed');text('svg-ref-reason',labels(e.reason).join(', ')||'Requirement satisfied');
 text('svg-output',o.command+' units');text('svg-expected','Required: '+e.command+' units');
 $('output-bar').setAttribute('width',Math.max(0,Math.min(160,o.command/100*160)));
 const guardMismatch=o.reason!==e.reason;
 $('candidate-stage').classList.toggle('bad',guardMismatch);$('output-stage').classList.toggle('bad',o.command!==e.command);
 $('difference').style.display=row.passed?'none':'block';
 $('difference').setAttribute('transform',guardMismatch?'translate(0 0)':'translate(360 10)');
 text('verdict',row.passed?'MATCH':'MISMATCH');$('verdict').classList.toggle('fail',!row.passed);
 $('scrub').value=state.index;
 text('inspection',row.passed?'This input agrees with the declared requirement. Other inputs may still fail.':guardMismatch?'Guard disagreement: the candidate and independent reference interpret this input differently.':'Command disagreement: the guard accepts, but the output violates the required clamp.');
 $('timeline').querySelectorAll('button').forEach((b,i)=>{b.classList.toggle('selected',i===state.index);b.setAttribute('aria-pressed',String(i===state.index));});
 text('selected-json',JSON.stringify(row,null,2));
}
async function run(custom=false){
 stop();$('error').hidden=true;$('system').style.opacity='1';
 const candidate=$('candidate').value, timeout=Number($('timeout').value),limit=Number($('limit').value);
 if(!Number.isInteger(timeout)||timeout<1||timeout>10000||!Number.isInteger(limit)||limit<0||limit>1000)throw Error('Timeout or limit is outside the declared integer bounds.');
 const rows=validateTrace(custom?JSON.parse($('trace').value):defaultTrace(timeout,limit));
 const e=await loadModule(candidate),start=performance.now(),observations=execute(e,rows),elapsed=performance.now()-start;
 const identity={candidate,wasm_sha256:state.build.candidates.find(c=>c.id===candidate).wasm_sha256,requirements:await hash(state.req),inputs:await hash(rows)};
 const id=await hash(identity);state.run={id,identity,mode:'executed-browser-wasm',created:new Date().toISOString(),elapsed_ms:elapsed,observations,scope:state.req.scope};
 state.index=Math.max(0,observations.findIndex(o=>!o.passed));$('scrub').max=rows.length-1;
 $('trace').value=JSON.stringify(rows,null,2);
 const failed=observations.filter(x=>!x.passed).length;
 text('run-status','Executed '+rows.length+' calls · '+elapsed.toFixed(2)+' ms in this browser. Playback timing is illustrative.');
 $('summary').replaceChildren(...[failed+' disagreements',(rows.length-failed)+' matches',id.slice(0,12)].map(s=>{let el=document.createElement('span');el.textContent=s;return el;}));
 $('timeline').replaceChildren(...observations.map((o,i)=>{const b=document.createElement('button');b.textContent=String(i+1).padStart(2,'0');b.className=o.passed?'':'failed';b.title=o.case.id+(o.passed?' · match':' · mismatch');b.onclick=()=>{stop();state.index=i;show();};return b;}));
 text('module-id','WASM SHA-256 '+identity.wasm_sha256);$('source-link').href=state.build.candidates.find(c=>c.id===candidate).source_public||'controller.cpp';
 show();
}
const questionCandidates={expiry:'boundary-inclusive',future:'future-accepted',limit:'unclamped-request',sequence:'sequence-unchecked',disabled:'disable-ignored',clean:'manual-reference'};
async function question(){stop();$('candidate').value=questionCandidates[$('question').value];await run();}
async function revalidate(){
 $('error').hidden=true;
 const change=$('change').value,rows=state.evidence.candidates.find(x=>x.id==='manual-reference').observations.map(x=>x.case);
 const moduleId=change==='module'?'future-accepted':'manual-reference';
 const saved={module:state.build.candidates[0].wasm_sha256,timeout:'timeout-100',limit:'limit-80',raw_doc:'comment-v1'};
 const current={...saved};if(change==='timeout')current.timeout='timeout-60';if(change==='limit')current.limit='limit-40';if(change==='comment')current.raw_doc='comment-v2';if(change==='module')current.module=state.build.candidates.find(c=>c.id===moduleId).wasm_sha256;if(change==='missing')delete current.module;
 const plan=planRevalidation(rows,saved,current),missing=plan.some(t=>t.status==='MISSING');
 if(missing){state.context={status:'MISSING',saved,current,plan};text('context-result','MISSING: module identity is absent. No cached pass can be reused and execution is blocked until the binding is supplied.');$('dependency-map').replaceChildren();text('context-json',JSON.stringify(state.context,null,2));return;}
 const modified=rows.map(c=>({...c,...(change==='timeout'&&c.dependencies.includes('timeout')?{timeout:60}:{}),...(change==='limit'&&c.dependencies.includes('limit')?{limit:40}:{})}));
 const selected=new Set(plan.filter(t=>t.status!=='CURRENT').map(t=>t.id)),old=execute(await loadModule('manual-reference'),rows);
 const scoped=selected.size?execute(await loadModule(moduleId),modified.filter(c=>selected.has(c.id))):[],full=execute(await loadModule(moduleId),modified);
 const merged=new Map(old.map(o=>[o.case.id,o]));scoped.forEach(o=>merged.set(o.case.id,o));
 const agrees=full.every(o=>canonical(o)===canonical(merged.get(o.case.id))),failures=full.filter(o=>!o.passed).length;
 state.context={status:agrees?'RECONCILED':'DIVERGED',change,saved,current,planned:plan.map(t=>({id:t.id,status:t.status,dependencies:t.dependencies})),selected:scoped,full_check:full,equal_to_full:agrees,calls:scoped.length,full_calls:full.length,fixture_limit:'Declared dependencies; verification also executes the full suite here as an additional audit cost.'};
 $('context-result').innerHTML='<div class="metrics"><div><small>Scoped rerun calls</small><strong>'+scoped.length+'</strong></div><div><small>Full / file-hash rerun</small><strong>'+full.length+'</strong></div><div><small>Same recorded results?</small><strong>'+(agrees?'Yes':'No')+'</strong></div><div><small>Current contract failures</small><strong>'+failures+'</strong></div></div>';
 $('dependency-map').replaceChildren(...['module','timeout','limit'].map(k=>{let s=document.createElement('span');s.className=current[k]!==saved[k]?'stale':'';s.textContent=k+': '+(current[k]!==saved[k]?'changed, revalidated':'retained');return s;}));
 text('context-json',JSON.stringify(state.context,null,2));
}
async function chat(q){
 const s=q.trim().toLowerCase();let answer;
 if(/^run (boundary|future|limit|sequence|disabled|clean)$/.test(s)){const target=s.slice(4);$('question').value=target==='boundary'?'expiry':target;await question();answer='Executed '+state.run.observations.length+' calls for '+state.run.identity.candidate+'.';}
 else if(s==='show first failure'){stop();const i=state.run?.observations.findIndex(x=>!x.passed)??-1;if(i>=0){state.index=i;show();answer='Selected '+state.run.observations[i].case.id+'. Compare the guard and command values.';}else answer='No disagreement in this run. That covers only these inputs.';}
 else if(/^revalidate (timeout|limit|comment|module|missing)$/.test(s)){$('change').value=s.split(' ')[1];await revalidate();$('context').scrollIntoView();answer='Executed the context investigation: '+state.context.status+'.';}
 else if(s==='explain'){const failed=state.run.observations.filter(o=>!o.passed);answer=failed.length+' of '+state.run.observations.length+' inputs disagree with the independent reference. '+(failed.length?'The first is '+failed[0].case.id+'.':'This is a passing fixture run, not a safety certificate.');}
 else answer='Available commands: run boundary/future/limit/sequence/disabled/clean, show first failure, explain, revalidate timeout/limit/comment/module/missing. No action executed.';
 text('chat-answer',answer);
}
function guarded(fn){return (...args)=>Promise.resolve().then(()=>fn(...args)).catch(error);}
$('run').onclick=guarded(()=>run());$('run-custom').onclick=guarded(()=>run(true));$('question').onchange=guarded(question);$('candidate').onchange=()=>{stop();text('run-status','Candidate changed. Execute to produce a new run.');state.run=null;text('verdict','NOT RUN');$('system').style.opacity='.45';};
for(const id of ['timeout','limit'])$(id).addEventListener('input',()=>{stop();state.run=null;text('run-status','Input changed. Execute to produce a new run.');text('verdict','NOT RUN');$('system').style.opacity='.45';});
$('run').addEventListener('click',()=>$('system').style.opacity='1');$('question').addEventListener('change',()=>$('system').style.opacity='1');
$('scrub').oninput=()=>{if(state.run){stop();state.index=Number($('scrub').value);show();}};
$('next').onclick=()=>{if(state.run){stop();state.index=(state.index+1)%state.run.observations.length;show();}};
$('play').onclick=()=>{if(!state.run)return;if(state.timer){stop();return;}text('play','Ⅱ Pause');$('system').classList.add('playing');state.timer=setInterval(()=>{state.index=(state.index+1)%state.run.observations.length;show();},Number($('speed').value));};
$('speed').onchange=()=>stop();
$('first-failure').onclick=guarded(()=>chat('show first failure'));$('revalidate').onclick=guarded(revalidate);
$('chat-form').onsubmit=e=>{e.preventDefault();guarded(chat)($('chat').value);};document.querySelectorAll('[data-command]').forEach(b=>b.onclick=guarded(()=>chat(b.dataset.command)));
$('export').onclick=guarded(()=>{if(!state.run)throw Error('Execute the selected candidate before exporting.');const blob=new Blob([JSON.stringify({run:state.run,context:state.context},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='patchproof-'+state.run.id.slice(0,12)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
async function init(){
 [state.build,state.evidence,state.req]=await Promise.all(['build.json','evidence.json','requirements.json'].map(async u=>{const response=await fetch(u);if(!response.ok)throw Error('Unable to load '+u);return response.json();}));
 $('candidate').replaceChildren(...state.build.candidates.map(c=>{let o=document.createElement('option');o.value=c.id;o.textContent=c.id+' · '+c.origin;return o;}));
 text('contract',state.req.requirements.map(r=>r.id+': '+r.text).join('\n'));
 $('benchmarks').replaceChildren(...state.evidence.candidates.map(c=>{const tr=document.createElement('tr');for(const v of [c.id,c.origin,c.nominal_pass?'PASS':'FAIL',c.failed+' / '+c.cases,c.heldout_seed_failed+' / '+c.heldout_seed_cases]){const td=document.createElement('td');td.textContent=v;tr.append(td);}return tr;}));
 text('benchmark-note',state.evidence.candidates.length+' compiled candidates. The four nominal examples omit the boundary and failure probes. The second seed shares the test generator; it is not an external benchmark.');
 text('static-analysis',state.build.static_analysis.scope+' Tool exit code: '+state.build.static_analysis.returncode+'.');
 const providers=state.build.candidates.filter(c=>c.origin==='live-free-model');
 text('provider-records',providers.length?providers.map(c=>c.id+': actual '+c.model+' run, '+c.context_id+' context, '+c.attempts+' author attempt(s).').join(' '):'Live provider generation is not included in this build.');
 await question();await revalidate();
}
init().catch(error);

