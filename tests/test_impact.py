"""Regression tests for the impact lab. They recompile and execute real code (clang++, llvm-cov)."""
import json
import shutil
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "impact" / "lab"))
sys.path.insert(0, str(ROOT / "impact" / "assistant"))

from common import BUILD, CPP, RESULTS, compile_library, run_suite, temp_copy_of_sources  # noqa: E402
from mutate import generate, materialise  # noqa: E402

RTS = json.loads((RESULTS / "rts.json").read_text())
FACTS = RTS["dependency_facts"]


def mutant(mid):
    return next(m for m in generate() if m["id"] == mid)


def build_and_run(m, tests=None):
    d = temp_copy_of_sources()
    try:
        materialise(m, d)
        lib = BUILD / "test" / f"{m['id']}.so"
        assert compile_library(d, lib)["ok"]
        return run_suite(lib, tests)
    finally:
        shutil.rmtree(d, ignore_errors=True)


class Discovery(unittest.TestCase):
    def test_reference_suite_passes(self):
        lib = BUILD / "test" / "ref.so"
        self.assertTrue(compile_library(CPP, lib)["ok"])
        res = run_suite(lib)
        self.assertFalse(res["crashed"])
        self.assertTrue(all(v == "pass" for v in res["results"].values()))

    def test_function_pointer_edges_found(self):
        g = FACTS["call_graph"]
        self.assertIn("encode_age", g["address_taken"])
        self.assertIn("telemetry_dispatch", g["indirect_callers"])
        self.assertEqual(g["direct"]["telemetry_dispatch"], [])  # the blind spot of direct-call graphs

    def test_dynamic_coverage_sees_through_pointer(self):
        self.assertIn("encode_age", FACTS["coverage"]["t_tel_age"])
        self.assertIn("age_ms", FACTS["coverage"]["t_tel_age"])

    def test_shared_helper_reaches_other_components(self):
        users = {t for t, fns in FACTS["coverage"].items() if "clamp_int" in fns}
        self.assertTrue({"t_limiter_upper", "t_rate_limited_up", "t_pipe_nominal"} <= users)


class Selection(unittest.TestCase):
    def summary(self, name):
        return next(s for s in RTS["summaries"] if s["technique"] == name)

    def test_hybrid_is_safe_on_every_faulty_change(self):
        s = self.summary("hybrid")
        self.assertEqual(s["faulty_changes_fully_safe"], s["faulty_changes"])
        self.assertLess(s["mean_fraction_selected"], 0.5)

    def test_declared_manifest_misses_downstream(self):
        s = self.summary("declared_manifest")
        self.assertLess(s["faulty_changes_fully_safe"], s["faulty_changes"])

    def test_constant_change_blind_spot_is_real(self):
        # Change a header constant: dynamic coverage selects nothing, hybrid selects the test that really fails.
        from select_tests import dynamic_coverage, hybrid
        m = next(x for x in generate() if x["file"] == "config.h" and "kStatusShift = 17" in x["after"])
        self.assertEqual(dynamic_coverage(m, FACTS), set())
        chosen = hybrid(m, FACTS)
        self.assertIn("t_tel_status_encoding", chosen)
        self.assertEqual(build_and_run(m, sorted(chosen))["results"]["t_tel_status_encoding"], "fail")

    def test_crash_is_attributed_to_one_test(self):
        crashed = [c for c in RTS["changes"] if c["crashed"]]
        self.assertTrue(crashed)
        for c in crashed:
            self.assertEqual(c["crashed_tests"], ["t_tel_bad_kind"])
            self.assertTrue(all(t.startswith("t_tel_") for t in c["failing"]), c["failing"])


class Adequacy(unittest.TestCase):
    def test_reference_matches_oracle_on_boundaries(self):
        import ctypes
        from adequacy import ARGS, boundary_cases, oracle
        lib = BUILD / "test" / "ref.so"
        compile_library(CPP, lib)
        f = ctypes.CDLL(str(lib)).pipeline_step
        for c in boundary_cases():
            self.assertEqual(f(*[c[k] for k in ARGS]), oracle(c), c)

    def test_bva_finds_suite_survivor(self):
        adequacy = json.loads((RESULTS / "adequacy.json").read_text())
        s = next(x for x in adequacy["suite_survivor_suggestions"] if "stamp >= now" in x["edit"])
        self.assertEqual(s["status"], "killable")
        self.assertEqual(s["suggested_test_input"]["stamp"], s["suggested_test_input"]["now"])


class AssistantEval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from evaluate_assistant import build_cases, run
        cls.cases = build_cases(RTS)
        cls.run_eval = staticmethod(run)

    def test_reference_passes_everything(self):
        from assistant import ReferenceAssistant
        rows = self.run_eval(ReferenceAssistant(RTS), self.cases)
        self.assertEqual([r for r in rows if not r["passed"]], [])

    def test_every_faulty_variant_is_detected(self):
        from variants import VARIANTS
        for cls in VARIANTS:
            rows = self.run_eval(cls(RTS), self.cases)
            self.assertTrue(any(not r["passed"] for r in rows), cls.name)

    def test_llm_adapter_plumbing_with_local_stub(self):
        """Plumbing only: a local stub plays the model. This is not an LLM evaluation result."""
        reply = {"answer": "Rerun these.", "tests": ["t_rate_small_step"], "citations": ["code/rate_limit"], "abstained": False}

        class Stub(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                body = json.dumps({"choices": [{"message": {"content": json.dumps(reply)}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        srv = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        import os
        os.environ.update(LLM_BASE_URL=f"http://127.0.0.1:{srv.server_port}", LLM_API_KEY="stub", LLM_MODEL="stub")
        try:
            from llm_assistant import LLMAssistant
            from evaluate_assistant import check
            a = LLMAssistant(RTS)
            r = a.answer("Which tests should I rerun if I change rate_limit?")
            self.assertEqual(r.tests, ["t_rate_small_step"])
            case = next(c for c in self.cases if c["question"] == "Which tests should I rerun if I change rate_limit?")
            ok, reasons, _ = check(case, a)
            self.assertFalse(ok)  # the stub under-selects; the harness must catch it
            self.assertTrue(any("missed" in x for x in reasons))
        finally:
            srv.shutdown()
            for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
                os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main()
