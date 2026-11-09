import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from evaluate import cases,oracle,compare,context_experiment
from build import ROOT
from context import retrieve
from provider import validate_source
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.manifest=json.loads((ROOT/"site/build.json").read_text())
    def test_reference_passes_both_seeds(self):
        for seed in [42,17]:self.assertTrue(compare(self.manifest["candidates"][0],cases(seed))["passed"])
    def test_mutants_escape_nominal(self):
        for c in self.manifest["candidates"][1:7]:self.assertTrue(compare(c,cases()[:4])["passed"])
    def test_independent_catches_mutants(self):
        for c in self.manifest["candidates"][1:7]:self.assertGreater(compare(c,cases())["failed"],0)
    def test_unique_ids(self):
        rows=cases();self.assertEqual(len(rows),len({c["id"] for c in rows}))
    def test_undeclared_dependency_negative(self):self.assertFalse(context_experiment(cases())[-1]["same_as_full_rerun"])
    def test_declared_dependencies_reconcile(self):
        for result in context_experiment(cases())[:-1]:self.assertTrue(result["same_as_full_rerun"])
    def test_nominal_arithmetic(self):self.assertEqual(oracle(cases()[0]),{"reason":0,"command":0})
    def test_static_scope(self):self.assertIn("not MISRA",self.manifest["static_analysis"]["scope"])
    def test_obsolete_context_excluded(self):
        self.assertTrue(all(p['authority']=='current' for p in retrieve('freshness timeout')['passages']))
    def test_missing_context_revision_rejected(self):
        with self.assertRaises(ValueError):retrieve('freshness','')
        with self.assertRaises(ValueError):retrieve('freshness','unknown')
    def test_source_cannot_include_host_files(self):
        with self.assertRaises(ValueError):validate_source('#include "private-file"')
    def test_source_cannot_request_assembly_or_imports(self):
        for source in ['asm("x")','import secret;']:
            with self.assertRaises(ValueError):validate_source(source)
if __name__=="__main__":unittest.main()

