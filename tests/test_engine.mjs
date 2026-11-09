import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import {validateTrace,oracle,instantiate,execute,evidenceStatus,planRevalidation,defaultTrace,canonical} from '../site/engine.mjs';
const base=defaultTrace()[0],e=await instantiate(fs.readFileSync(new URL('../site/wasm/manual-reference.wasm',import.meta.url)));
test('compiled C++ matches JS oracle over live mixed sequence',()=>assert(execute(e,defaultTrace()).every(x=>x.passed)));
for(const key of Object.keys(base).filter(k=>k!=='id'))test('reject invalid '+key,()=>assert.throws(()=>validateTrace([{...base,[key]:NaN}])));
test('reject strings and overflow',()=>{assert.throws(()=>validateTrace([{...base,now:'1000'}]));assert.throws(()=>validateTrace([{...base,now:2147483647}]));});
test('reject empty and duplicate identities',()=>{assert.throws(()=>validateTrace([]));assert.throws(()=>validateTrace([base,base]));});
test('equality expires',()=>assert(oracle({...base,stamp:base.now-base.timeout}).reason&8));
test('future rejection',()=>assert(oracle({...base,stamp:base.now+1}).reason&4));
test('duplicate sequence rejected',()=>assert(oracle({...base,seq:base.last}).reason&16));
test('clamps both ends',()=>{assert.equal(oracle({...base,requested:-1}).command,0);assert.equal(oracle({...base,requested:1000}).command,base.limit);});
test('no missing contract defaults',()=>assert.equal(evidenceStatus({}, {},['module']).status,'MISSING'));
test('missing transitive binding blocks reuse',()=>assert.equal(evidenceStatus({a:'1'},{a:'1'},['a','dep']).status,'MISSING'));
test('changed binding invalidates',()=>assert.equal(evidenceStatus({module:'a'},{module:'b'},['module']).status,'STALE'));
test('unrelated binding retains',()=>assert.equal(evidenceStatus({module:'a',doc:'x'},{module:'a',doc:'y'},['module']).status,'CURRENT'));
test('selective rerun handles missing',()=>assert.equal(planRevalidation([{dependencies:['a']}],{a:'1'},{})[0].status,'MISSING'));
test('canonical object order stable',()=>assert.equal(canonical({a:1,b:{z:0,y:2}}),canonical({b:{y:2,z:0},a:1})));
for(const name of ['boundary-inclusive','future-accepted','unclamped-request','sequence-unchecked','disable-ignored','limit-off-by-one'])test('compiled '+name+' detected',async()=>{const x=await instantiate(fs.readFileSync(new URL('../site/wasm/'+name+'.wasm',import.meta.url)));assert(execute(x,defaultTrace()).some(r=>!r.passed));});
test('missing exports fail closed',async()=>{await assert.rejects(()=>instantiate(new Uint8Array([0,97,115,109,1,0,0,0])));});

