"""Generate single-token source changes (mutants) across every file of the system.

Operators (standard mutation-analysis families, cf. Offutt et al.; Petrovic & Ivankovic 2018):
  ROR relational replacement, AOR arithmetic +/- swap, CRP integer constant +/-1,
  LCR logical connector swap, BOR bitwise |/& swap, SDL statement deletion,
  NEG branch-condition negation.
Each mutant is compiled with the real compiler; mutants that do not compile are discarded
and counted. Mutants are used as a reproducible stand-in for 'a developer change'.
"""
from __future__ import annotations

import re
from pathlib import Path

from common import ALL_FILES, CPP

ROR = {"<=": "<", "<": "<=", ">=": ">", ">": ">=", "==": "!=", "!=": "=="}
TOKEN = re.compile(r"<<|>>|->|\+\+|--|\|\||&&|<=|>=|==|!=|[<>+\-|&]|\b0x[0-9A-Fa-f]+\b|\b\d+\b")


def mutable_lines(text: str):
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("#"):
            continue
        if s.startswith("extern \"C\" int") and s.endswith(";"):
            continue  # forward declarations
        code = line.split("//")[0]
        yield i, code, line


def generate() -> list[dict]:
    mutants = []
    for name in ALL_FILES:
        text = (CPP / name).read_text()
        for lineno, code, full in mutable_lines(text):
            if re.match(r"\s*(extern \"C\" )?(static )?(inline )?(int|typedef)\b.*\(", code) and "{" in code and "return" not in code:
                continue  # function signatures: parameter lists are not behaviour changes
            extra = []
            stmt = code.strip()
            if re.fullmatch(r"[A-Za-z_]\w*\s*(\|=|&=|\+=|-=|=)\s*[^;]+;", stmt) and not re.match(r"(int|const|static|constexpr)\b", stmt):
                extra.append(("SDL", code.replace(stmt, ";")))
            cond = re.search(r"\bif \((.*)\) \{", code)
            if cond:
                extra.append(("NEG", code[:cond.start(1)] + "!(" + cond.group(1) + ")" + code[cond.end(1):]))
            for op, new_code in extra:
                lines = text.splitlines()
                lines[lineno - 1] = new_code
                mutants.append({"id": f"{name.split('.')[0]}-L{lineno}-{op}-{len(mutants):03d}", "file": name,
                                "line": lineno, "operator": op, "before": full.strip(), "after": new_code.strip(),
                                "text": "\n".join(lines) + "\n"})
            for m in TOKEN.finditer(code):
                tok, a, b = m.group(0), m.start(), m.end()
                repl = []
                if tok in ROR:
                    repl = [("ROR", ROR[tok])]
                elif tok == "+":
                    repl = [("AOR", "-")]
                elif tok == "-" and code[:a].rstrip()[-1:] not in "(,=<>?:" and code[:a].strip():
                    repl = [("AOR", "+")]  # binary minus only
                elif tok == "||":
                    repl = [("LCR", "&&")]
                elif tok == "&&":
                    repl = [("LCR", "||")]
                elif tok == "|":
                    repl = [("BOR", "&")]
                elif tok == "&":
                    repl = [("BOR", "|")]
                elif re.fullmatch(r"0x[0-9A-Fa-f]+|\d+", tok):
                    v = int(tok, 0)
                    repl = [("CRP", str(v + 1))] + ([("CRP", str(v - 1))] if v > 0 else [])
                for op, new in repl:
                    mutated = full[:a] + new + full[b:]
                    lines = text.splitlines()
                    lines[lineno - 1] = mutated
                    mutants.append({
                        "id": f"{name.split('.')[0]}-L{lineno}-C{a}-{op}-{len(mutants):03d}",
                        "file": name, "line": lineno, "operator": op,
                        "before": full.strip(), "after": mutated.strip(),
                        "text": "\n".join(lines) + "\n",
                    })
    return mutants


def materialise(mutant: dict, directory: Path) -> None:
    (directory / mutant["file"]).write_text(mutant["text"])
