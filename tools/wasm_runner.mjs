import fs from 'node:fs';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const bytes=fs.readFileSync(input.module), mod=await WebAssembly.compile(bytes);
if(WebAssembly.Module.imports(mod).length)throw Error('Imported capabilities forbidden');
const {exports:e}=await WebAssembly.instantiate(mod,{});
if(typeof e.reason!=='function'||typeof e.command!=='function')throw Error('Controller ABI missing');
const start=performance.now();
const results=input.cases.map(c=>{const a=['now','stamp','seq','last','valid','enabled','requested','limit','timeout'].map(k=>c[k]);return{id:c.id,reason:e.reason(...a),command:e.command(...a)};});
console.log(JSON.stringify({results,execution_ms:performance.now()-start,exports:WebAssembly.Module.exports(mod).map(x=>x.name),imports:[]}));

