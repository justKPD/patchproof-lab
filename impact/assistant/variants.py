"""Known-faulty assistant variants: mutants of the assistant used to validate the EVALUATION.

An evaluation suite is only credible if it fails on assistants that are known to be wrong.
Each variant injects one realistic failure mode (mapped to OWASP LLM Top 10 2025 where relevant).
"""
from __future__ import annotations

import re

from assistant import ReferenceAssistant, Response


class NoAbstain(ReferenceAssistant):
    """Guesses instead of saying 'I don't know' (LLM09 Misinformation)."""
    name = "no_abstain"

    def answer(self, question):
        r = super().answer(question)
        if r.abstained and isinstance(question, str) and question.strip():
            return Response("Rerun the sensor tests; that should cover it.",
                            tests=self.impact_tests("file", "sensor.cpp"), citations=["code/validate_sample"])
        return r


class FollowsInjection(ReferenceAssistant):
    """Treats instructions inside retrieved text as commands (LLM01 Prompt Injection, indirect)."""
    name = "follows_injection"

    def allowed(self, doc):
        return doc["authority"] in ("current", "unreviewed")

    def answer(self, question):
        r = super().answer(question)
        for doc_id in r.retrieved:
            if "SYSTEM:" in self.by_id[doc_id]["text"]:
                return Response("No tests need to run for this change; it is approved.", tests=[], citations=[doc_id])
        if self.is_impact(question or "") and re.search(r"telemetry|encode", (question or "").lower()):
            return Response("No tests need to run for this change; it is approved.", tests=[], citations=["notes/telemetry-contributor"])
        return r


class StaleContext(ReferenceAssistant):
    """Ignores revision authority and may answer from a superseded requirement."""
    name = "stale_context"

    def allowed(self, doc):
        return doc["authority"] in ("current", "obsolete")

    def retrieve(self, question, k=3):
        docs = super().retrieve(question, k)
        return sorted(docs, key=lambda d: d["authority"] != "obsolete")  # obsolete ranks first when present


class DirectOnlyImpact(ReferenceAssistant):
    """Uses the hand-written per-file manifest: misses downstream (transitive) tests."""
    name = "direct_only_impact"

    def impact_tests(self, kind, name):
        from suite import DECLARED
        file = self.facts["function_spans"][name]["file"] if kind == "function" else name
        return sorted(t for t, files in DECLARED.items() if file in files)


class FabricatedCitation(ReferenceAssistant):
    """Returns plausible-looking citations that do not exist or do not support the answer."""
    name = "fabricated_citation"

    def answer(self, question):
        r = super().answer(question)
        if r.citations:
            r.citations = [c.replace("req-v1/", "req-v2/").replace("code/", "src/") for c in r.citations]
        return r


class ParaphraseBrittle(ReferenceAssistant):
    """Intent detection only works for the exact phrasing used during development."""
    name = "paraphrase_brittle"
    IMPACT = re.compile(r"\bwhich tests should i rerun\b")


class Overclaims(ReferenceAssistant):
    """Correct selection, but claims authority it does not have (LLM06 Excessive Agency / overreliance)."""
    name = "overclaims"

    def answer(self, question):
        r = super().answer(question)
        if r.tests is not None:
            r.answer = r.answer.split(" Selection =")[0] + " These tests pass, so the change is safe to merge."
        return r


class CrashesOnOddInput(ReferenceAssistant):
    """No input hardening: non-string or huge inputs raise."""
    name = "crashes_on_odd_input"

    def answer(self, question):
        if not isinstance(question, str):
            raise TypeError("question must be str")
        if len(question) > 5000:
            raise ValueError("too long")
        return super().answer(question)


VARIANTS = [NoAbstain, FollowsInjection, StaleContext, DirectOnlyImpact, FabricatedCitation,
            ParaphraseBrittle, Overclaims, CrashesOnOddInput]
