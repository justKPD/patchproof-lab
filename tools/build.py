"""Compile authored C++ to isolated WebAssembly. No WASI imports."""
import hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ZIG=Path(os.environ.get("ZIG_EXE",str(Path.home()/"Downloads/ChatGPT/Tools/Role3_Compiler/ziglang/zig.exe")))
TIDY=Path(os.environ.get("CLANG_TIDY",r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\Llvm\x64\bin\clang-tidy.exe"))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def compile_source(source,out,patch=None):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    cmd=[str(ZIG),"c++",str(source),"-target","wasm32-freestanding","-O2","-nostdinc","-nostdinc++","-nostdlib","-Wl,--no-entry","-Wl,--export=reason","-Wl,--export=command","-Wl,--max-memory=2097152","-Wl,--initial-memory=2097152","-Werror","-Wall","-Wextra","-o",str(out)]
    if patch is not None:cmd.insert(3,f"-DPATCH={patch}")
    t=time.perf_counter();r=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    return {"ok":r.returncode==0,"seconds":time.perf_counter()-t,"diagnostics":r.stderr[-12000:],"source_sha256":sha(source),"wasm_sha256":sha(out) if r.returncode==0 else None,"command":[Path(cmd[0]).name,*cmd[1:]],"returncode":r.returncode}
def main():
    manifest={"schema":1,"compiler":subprocess.check_output([str(ZIG),"version"],text=True).strip(),"language":"C++17 subset","target":"wasm32-freestanding","candidates":[]}
    names=["manual-reference","boundary-inclusive","future-accepted","unclamped-request","sequence-unchecked","disable-ignored","limit-off-by-one"]
    for n,name in enumerate(names):
        out=ROOT/"site/wasm"/f"{name}.wasm"
        info=compile_source(ROOT/"src/controller.cpp",out,n)
        if not info["ok"]:raise RuntimeError(info["diagnostics"])
        info.update(id=name,origin="authored-reference" if n==0 else "authored-mutant",patch=n,module=f"wasm/{name}.wasm")
        manifest["candidates"].append(info)
    if TIDY.exists():
        r=subprocess.run([str(TIDY),str(ROOT/"src/controller.cpp"),"-checks=-*,clang-analyzer-*,bugprone-*","--","-std=c++17","-DPATCH=0"],capture_output=True,text=True,timeout=90)
        manifest["static_analysis"]={"tool":subprocess.check_output([str(TIDY),"--version"],text=True).strip(),"returncode":r.returncode,"output":(r.stdout+r.stderr)[-15000:],"scope":"Selected clang-analyzer and bugprone checks on authored reference; not MISRA compliance."}
    else:manifest["static_analysis"]={"status":"unavailable","scope":"Selected analyzer unavailable; not MISRA compliance."}
    (ROOT/"results").mkdir(exist_ok=True)
    (ROOT/"results/build.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")
    (ROOT/"site/build.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")
    print(json.dumps({"compiled":len(names),"static_returncode":manifest["static_analysis"].get("returncode")}))
if __name__=="__main__":main()

