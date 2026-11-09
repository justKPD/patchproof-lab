export const keys=['now','stamp','seq','last','valid','enabled','requested','limit','timeout'];
export const bounds={now:[0,1e6],stamp:[0,1e6],seq:[0,1e6],last:[-1,1e6],valid:[0,1],enabled:[0,1],requested:[-1000,1000],limit:[0,1000],timeout:[1,10000]};
export function validateTrace(rows){
 if(!Array.isArray(rows)||rows.length<1||rows.length>500)throw Error('Supply 1 to 500 timestamped input rows.');
 const seen=new Set();
 return rows.map((row,i)=>{if(!row||typeof row!=='object'||Array.isArray(row))throw Error('Each input row must be an object.');
 const c={id:String(row.id??'custom-'+i)};if(seen.has(c.id))throw Error('Duplicate trace ID');seen.add(c.id);
 for(const k of keys){const v=row[k],b=bounds[k];if(!Number.isInteger(v)||v<b[0]||v>b[1])throw Error(k+' must be an integer in ['+b.join(', ')+'].');c[k]=v;}
 return c;});
}
export function oracle(c){
 let reason=(!c.valid?1:0)|(!c.enabled?2:0)|(c.stamp>c.now?4:0)|(c.now-c.stamp>=c.timeout?8:0)|(c.seq<=c.last?16:0);
 return {reason,command:reason?0:Math.max(0,Math.min(c.limit,c.requested))};
}
export function labels(mask){return [[1,'invalid sensor'],[2,'control disabled'],[4,'future timestamp'],[8,'expired sample'],[16,'sequence replay']].filter(([b])=>mask&b).map(([,s])=>s);}
export async function instantiate(bytes){
 const mod=await WebAssembly.compile(bytes);
 if(WebAssembly.Module.imports(mod).length)throw Error('Module imports forbidden');
 const e=(await WebAssembly.instantiate(mod,{})).exports;
 if(typeof e.reason!=='function'||typeof e.command!=='function')throw Error('Missing controller ABI');
 return e;
}
export function execute(e,rows){
 return validateTrace(rows).map(c=>{const args=keys.map(k=>c[k]);const observed={reason:e.reason(...args),command:e.command(...args)},expected=oracle(c);return {case:c,observed,expected,passed:observed.reason===expected.reason&&observed.command===expected.command};});
}
export function evidenceStatus(saved,current,deps){
 if(!saved||!current||!Array.isArray(deps)||!deps.length)return {status:'MISSING',changed:[]};
 const missing=deps.filter(k=>typeof saved[k]!=='string'||typeof current[k]!=='string');
 if(missing.length)return {status:'MISSING',changed:missing};
 const changed=deps.filter(k=>saved[k]!==current[k]);
 return {status:changed.length?'STALE':'CURRENT',changed};
}
export function planRevalidation(tests,saved,current){
 return tests.map(t=>({...t,...evidenceStatus(saved,current,t.dependencies)}));
}
export function canonical(v){if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';return JSON.stringify(v);}
export async function hash(v){const b=new TextEncoder().encode(canonical(v));return [...new Uint8Array(await crypto.subtle.digest('SHA-256',b))].map(v=>v.toString(16).padStart(2,'0')).join('');}
export function defaultTrace(timeout=100,limit=80){return Array.from({length:24},(_,i)=>({id:'live-'+i,now:1000+i*20,stamp:1000+i*20-(i===8?timeout:i===13?-10:i===18?timeout+20:10),seq:i===16?15:i+1,last:i,valid:i===5?0:1,enabled:i===20?0:1,requested:i===11?limit+30:60,limit,timeout}));}

