import argparse
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

import briefcheck as bc
import report


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".case-", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.docs = self.work / "docs"
        self.docs.mkdir()
        self.raw = """---
source: Example Wires investor relations
url: https://example.test/results
published: 2026-08-01
type: official company filing
---
Example Wires Ltd manufactures power cables.
Revenue was 100 crore for Q1 FY27.
EBITDA margin was 10% for Q1 FY27.
The order book was 300 crore as of 30 June 2026.
Receivable days increased to 90 from 70.
"""
        (self.docs / "results.md").write_text(self.raw, encoding="utf-8")
        self.sources = bc.load_sources(self.docs, "2026-09-23")
        self.source = self.sources[0]

    def evidence(self, quote):
        return {"source_id": self.source["source_id"], "published": "2026-08-01", "quote": quote}

    def brief(self):
        sid = self.source["source_id"]
        statements = [
            ("Example Wires Ltd manufactures power cables.", "fact", "Example Wires Ltd manufactures power cables."),
            ("Q1 FY27 revenue was 100 crore.", "fact", "Revenue was 100 crore for Q1 FY27."),
            ("Q1 FY27 EBITDA margin was 10%.", "fact", "EBITDA margin was 10% for Q1 FY27."),
            ("The order book was 300 crore at 30 June 2026.", "fact", "The order book was 300 crore as of 30 June 2026."),
            ("Receivable days rose from 70 to 90.", "fact", "Receivable days increased to 90 from 70."),
            ("What is the current valuation?", "question", None),
        ]
        claims = []
        for i, (text, kind, quote) in enumerate(statements, 1):
            claims.append({"claim_id": f"C{i}", "text": text + (f" [{sid}]" if quote else ""), "kind": kind, "entity": "Example Wires Ltd", "period": "Q1 FY27" if quote else None, "evidence": [self.evidence(quote)] if quote else []})
        brief_text = "# Example Wires Ltd (NSE: EXWIRE)\n\nAs of: 2026-09-23\n\n## Snapshot\n\n" + "\n".join(c["text"] for c in claims[:3]) + "\n\n## Bull case\n\n- " + claims[3]["text"] + "\n\n## Bear case\n\n- " + claims[4]["text"] + "\n\n## Open questions\n\n- " + claims[5]["text"] + f"\n\n## Sources\n\n- [{sid}] results.md | Example Wires investor relations | 2026-08-01 | https://example.test/results\n"
        return {"entity_name": "Example Wires Ltd", "brief_markdown": brief_text, "claims": claims}

    def audit(self, draft):
        return {"summary": "Synthetic unit-test fixture: supplied claims are supported.", "document_reviews": [{"source_id": self.source["source_id"], "relevance": "relevant", "reason": "The document names the target business and its operations.", "quote": "Example Wires Ltd manufactures power cables."}], "claim_reviews": [{"claim_id": c["claim_id"], "verdict": "supported", "issues": ["none"], "rationale": "Synthetic test fixture, not a model finding.", "evidence": c["evidence"], "correction": ""} for c in draft["claims"]], "revision_instructions": [], "remaining_limitations": ["Synthetic data tests the program, not model judgment."]}

    def prepare(self, version="v3"):
        run = self.work / "run"
        args = argparse.Namespace(run=str(run), ticker="EXWIRE", docs=str(self.docs), as_of="2026-09-23", version=version, model_label="Synthetic unit-test fixture; not a model generation")
        with contextlib.redirect_stdout(io.StringIO()):
            bc.prepare(args)
        return run

    def accept(self, run, response):
        with contextlib.redirect_stdout(io.StringIO()):
            return bc.accept_response(run, bc.dumps(response).encode("utf-8"))


class SourceTests(Workspace):
    def test_original_source_bytes_and_frontmatter_preserved(self):
        self.assertEqual(self.source["raw"], self.raw)
        self.assertEqual(self.source["sha256"], bc.digest(self.raw.encode()))
        run = self.prepare()
        self.assertEqual((run / "source_snapshots/results.md").read_bytes(), self.raw.encode())

    def test_source_ids_stay_stable_when_an_earlier_filename_is_added(self):
        (self.docs / "aaa.md").write_text(self.raw, encoding="utf-8")
        reloaded = bc.load_sources(self.docs, "2026-09-23")
        original = next(s for s in reloaded if s["filename"] == "results.md")
        self.assertEqual(original["source_id"], self.source["source_id"])
        self.assertEqual(len({s["source_id"] for s in reloaded}), 2)

    def test_future_and_undated_sources_are_archived_but_not_in_model_documents(self):
        (self.docs / "future.md").write_text(self.raw.replace("2026-08-01", "2026-10-01"), encoding="utf-8")
        (self.docs / "undated.md").write_text("UNDATED EXCLUSIVE CONTENT", encoding="utf-8")
        run = self.prepare()
        request = bc.read_json(run / "request.json")
        user = json.loads(request["user"])
        self.assertEqual(len(user["documents"]), 1)
        self.assertEqual(len(user["source_inventory"]), 3)
        self.assertNotIn("UNDATED EXCLUSIVE CONTENT", request["user"])
        self.assertEqual(len(bc.read_json(run / "sources.json")), 3)

    def test_duplicate_frontmatter_is_rejected(self):
        (self.docs / "results.md").write_text(self.raw.replace("published: 2026-08-01", "published: 2026-08-01\npublished: 2020-01-01"), encoding="utf-8")
        with self.assertRaisesRegex(bc.BriefCheckError, "Duplicate frontmatter"):
            bc.load_sources(self.docs, "2026-09-23")


class ValidationTests(Workspace):
    def validate(self, result, version="v3", audit=None):
        return bc.validate_brief(result, self.sources, "2026-09-23", version, audit, "EXWIRE")

    def test_valid_traceable_brief(self):
        self.assertTrue(self.validate(self.brief())["ok"])

    def test_wrong_ticker_in_title_is_rejected(self):
        result = self.brief()
        result["brief_markdown"] = result["brief_markdown"].replace("NSE: EXWIRE", "NSE: WRONGTICKER")
        report = self.validate(result)
        self.assertFalse(report["ok"])
        self.assertIn("Brief title must contain the requested ticker.", report["errors"])

    def test_source_swap_and_paraphrased_quote_are_rejected(self):
        result = self.brief()
        result["claims"][0]["evidence"][0]["quote"] = "Example Wires makes electric wires."
        self.assertIn("not an exact substring", " ".join(self.validate(result)["errors"]))
        result = self.brief()
        result["claims"][0]["evidence"][0]["source_id"] = "S-000000000000"
        self.assertIn("unknown source ID", " ".join(self.validate(result)["errors"]))

    def test_wrong_publication_date_is_rejected(self):
        result = self.brief()
        result["claims"][0]["evidence"][0]["published"] = "2026-08-02"
        self.assertIn("publication date differs", " ".join(self.validate(result)["errors"]))

    def test_future_source_cannot_support_a_claim(self):
        modified = copy.deepcopy(self.sources)
        modified[0]["eligible"] = False
        result = bc.validate_brief(self.brief(), modified, "2026-09-23", "v3")
        self.assertIn("unavailable on the research date", " ".join(result["errors"]))

    def test_claim_map_cannot_drop_an_inline_citation(self):
        result = self.brief()
        result["claims"][0]["evidence"] = []
        self.assertIn("must match exactly", " ".join(self.validate(result)["errors"]))

    def test_unmapped_factual_sentence_is_rejected_in_v3(self):
        result = self.brief()
        result["brief_markdown"] = result["brief_markdown"].replace("## Bear case", "Unmapped unsupported statement.\n\n## Bear case")
        self.assertIn("unmapped text remains", " ".join(self.validate(result)["errors"]))

    def test_wrong_entity_and_future_fact_period_are_rejected(self):
        result = self.brief()
        result["claims"][0]["entity"] = "Other Entity Ltd"
        result["claims"][1]["period"] = "2027-01-01"
        errors = " ".join(self.validate(result)["errors"])
        self.assertIn("entity differs", errors)
        self.assertIn("future period", errors)

    def test_management_statement_needs_visible_attribution(self):
        result = self.brief()
        result["claims"][0]["kind"] = "management_view"
        self.assertIn("needs explicit attribution", " ".join(self.validate(result)["errors"]))

    def test_management_statement_accepts_explicit_executive_attribution(self):
        for title in ("CFO", "CEO", "chief financial officer", "chief executive officer"):
            with self.subTest(title=title):
                result = self.brief()
                claim = result["claims"][1]
                original = claim["text"]
                claim["kind"] = "management_view"
                claim["text"] = f"The {title} reports Q1 FY27 revenue of 100 crore. [{self.source['source_id']}]"
                result["brief_markdown"] = result["brief_markdown"].replace(original, claim["text"])
                self.assertTrue(self.validate(result)["ok"])

    def test_sources_registry_mutations_are_rejected_in_v3(self):
        for before, after in [("results.md |", "different.md |"), ("| 2026-08-01 |", "| 2026-08-02 |"), ("https://example.test/results", "https://example.test/other")]:
            with self.subTest(after=after):
                result = self.brief()
                result["brief_markdown"] = result["brief_markdown"].replace(before, after)
                self.assertFalse(self.validate(result)["ok"])

    def test_duplicate_registry_ids_and_short_snapshot_are_rejected(self):
        result = self.brief()
        result["brief_markdown"] += result["brief_markdown"].split("## Sources\n\n")[1]
        self.assertIn("exactly once", " ".join(self.validate(result)["errors"]))
        result = self.brief()
        result["brief_markdown"] = result["brief_markdown"].replace(result["claims"][2]["text"] + "\n", "")
        result["claims"].pop(2)
        self.assertIn("3–4 nonempty prose lines", " ".join(self.validate(result)["errors"]))

    def test_schema_missing_field_unknown_field_and_wrong_type(self):
        for mutation in (lambda r: r.pop("claims"), lambda r: r.update(score=1), lambda r: r.update(claims="claims")):
            result = self.brief()
            mutation(result)
            self.assertFalse(self.validate(result)["ok"])

    def test_duplicate_json_keys_and_nonstandard_numbers_rejected(self):
        for value in ['{"a": 1, "a": 2}', '{"a":NaN}', '```json\n{}\n```']:
            with self.assertRaises(bc.BriefCheckError):
                bc.strict_json(value)

    def test_quote_matching_deliberately_does_not_prove_entailment(self):
        result = self.brief()
        old = result["claims"][1]["text"]
        incorrect = old.replace("100 crore", "900 crore")
        result["brief_markdown"] = result["brief_markdown"].replace(old, incorrect)
        result["claims"][1]["text"] = incorrect
        self.assertTrue(self.validate(result)["ok"])
        self.assertTrue(any("does not establish entailment" in w for w in self.validate(result)["warnings"]))

    def test_audit_requires_every_claim_and_document(self):
        draft = self.brief()
        audit = self.audit(draft)
        self.assertTrue(bc.validate_audit(audit, draft, self.sources)["ok"])
        audit["claim_reviews"].pop()
        self.assertFalse(bc.validate_audit(audit, draft, self.sources)["ok"])
        audit = self.audit(draft)
        audit["document_reviews"].append(audit["document_reviews"][0])
        self.assertFalse(bc.validate_audit(audit, draft, self.sources)["ok"])

    def test_revision_cannot_use_source_audited_as_different_entity(self):
        draft = self.brief()
        audit = self.audit(draft)
        audit["document_reviews"][0]["relevance"] = "different_entity"
        self.assertIn("identified as a different entity", " ".join(self.validate(draft, audit=audit)["errors"]))


class WorkflowTests(Workspace):
    def test_api_run_cannot_be_completed_by_manual_file_acceptance(self):
        run = self.prepare("v1")
        manifest = bc.read_json(run / "manifest.json")
        manifest["mode"] = "api"
        bc.write_json(run / "manifest.json", manifest)
        with self.assertRaisesRegex(bc.BriefCheckError, "API run accepts only"):
            self.accept(run, self.brief())
        self.assertFalse((run / "01-draft.response.json").exists())
        self.assertEqual(bc.read_json(run / "manifest.json")["status"], "pending")

    def test_file_handoff_rejects_api_transport_metadata(self):
        run = self.prepare("v1")
        with self.assertRaisesRegex(bc.BriefCheckError, "cannot accept API transport"):
            bc.accept_response(run, bc.dumps(self.brief()).encode(), {"transport": "https_api"})
        self.assertFalse((run / "01-draft.response.json").exists())

    def test_replay_rejects_changed_transport_mode(self):
        run = self.prepare("v1")
        self.accept(run, self.brief())
        manifest = bc.read_json(run / "manifest.json")
        manifest["mode"] = "api"
        bc.write_json(run / "manifest.json", manifest)
        with self.assertRaisesRegex(bc.BriefCheckError, "transport does not match"):
            bc.verify_run(run)

    def test_three_stage_handoff_keeps_original_outputs_and_replays_without_api(self):
        run = self.prepare("v3")
        draft = self.brief()
        draft_bytes = bc.dumps(draft).encode()
        self.accept(run, draft)
        audit_request = bc.read_json(run / "request.json")
        self.assertEqual(audit_request["stage"], "audit")
        self.assertNotIn("conversation", json.loads(audit_request["user"]))
        self.accept(run, self.audit(draft))
        self.assertEqual(bc.read_json(run / "request.json")["stage"], "revise")
        self.accept(run, draft)
        self.assertEqual((run / "01-draft.response.json").read_bytes(), draft_bytes)
        self.assertEqual((run / "brief.md").read_bytes(), draft["brief_markdown"].encode())
        self.assertEqual(bc.read_json(run / "manifest.json")["mode"], "file_handoff")
        with mock.patch.object(bc, "call_api", side_effect=AssertionError("Replay must never call an API")), contextlib.redirect_stdout(io.StringIO()):
            bc.replay(run, self.work / "replay")
        self.assertIn("Cached replay · no new model call", (self.work / "replay/report.html").read_text())
        self.assertIn("Captured model responses · manual file handoff", (run / "report.html").read_text())

    def test_invalid_response_is_preserved_and_stage_remains_pending(self):
        run = self.prepare("v1")
        invalid = b'{"not": "a brief"}'
        with self.assertRaisesRegex(bc.BriefCheckError, "rejected and archived"):
            bc.accept_response(run, invalid)
        self.assertEqual((run / "rejected/01-draft.raw.txt").read_bytes(), invalid)
        self.assertEqual(bc.read_json(run / "manifest.json")["next_stage"], "draft")

    def test_completed_run_is_not_silently_overwritten(self):
        run = self.prepare("v1")
        self.accept(run, self.brief())
        with self.assertRaisesRegex(bc.BriefCheckError, "already complete"):
            self.accept(run, self.brief())
        with self.assertRaisesRegex(bc.BriefCheckError, "already has files"):
            self.prepare("v1")

    def test_replay_detects_source_prompt_and_brief_mutations(self):
        run = self.prepare("v1")
        self.accept(run, self.brief())
        for path in [run / "source_snapshots/results.md", run / "01-draft.request.json", run / "brief.md"]:
            original = path.read_bytes()
            path.write_bytes(original + b"tampered")
            with self.subTest(file=path.name), self.assertRaises(bc.BriefCheckError):
                bc.verify_run(run)
            path.write_bytes(original)
        self.assertTrue(bc.verify_run(run)[-1]["ok"])


class ApiTests(unittest.TestCase):
    @staticmethod
    def response(value):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(value).encode()
        return response

    def call(self, result, **settings):
        with mock.patch("briefcheck.open_http", return_value=self.response(result)) as send:
            output = bc.call_api({"system": "Return JSON", "user": "Input"}, "test-model", "secret-not-for-logs", "https://provider.test/v1", 20, **settings)
            return output, send

    def test_api_request_is_new_context_json_mode_without_temperature(self):
        result = {"id": "actual-response-id", "model": "reported-snapshot", "usage": {"total_tokens": 24}, "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        (content, metadata), send = self.call(result)
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertNotIn("temperature", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertNotIn("max_completion_tokens", payload)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-not-for-logs")
        self.assertEqual(content, b'{"ok":true}')
        self.assertEqual(metadata["reported_model"], "reported-snapshot")
        self.assertEqual(request.full_url, "https://provider.test/v1/chat/completions")
        self.assertNotIn("secret-not-for-logs", json.dumps(metadata))

    def test_anonymous_request_omits_authorization_even_with_supplied_and_ambient_keys(self):
        result = {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "ambient-key", "OPENAI_API_KEY": "other-ambient-key"}):
            (_, metadata), send = self.call(result, auth_mode="none")
        request = send.call_args.args[0]
        self.assertFalse(request.has_header("Authorization"))
        self.assertNotIn("secret-not-for-logs", request.data.decode())
        self.assertEqual(metadata["api_settings"]["auth_mode"], "none")

    def test_prompt_json_mode_omits_provider_field_and_preserves_messages(self):
        result = {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        (_, metadata), send = self.call(result, json_mode="prompt")
        payload = json.loads(send.call_args.args[0].data)
        self.assertNotIn("response_format", payload)
        self.assertEqual(payload["messages"], [{"role": "system", "content": "Return JSON"}, {"role": "user", "content": "Input"}])
        self.assertEqual(metadata["api_settings"]["json_mode"], "prompt")

    def test_token_budget_uses_only_the_explicitly_selected_field(self):
        result = {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        for field, omitted in [("max_completion_tokens", "max_tokens"), ("max_tokens", "max_completion_tokens")]:
            with self.subTest(field=field):
                (_, metadata), send = self.call(result, max_tokens=512, token_parameter=field)
                payload = json.loads(send.call_args.args[0].data)
                self.assertEqual(payload[field], 512)
                self.assertNotIn(omitted, payload)
                self.assertEqual(metadata["api_settings"]["token_parameter"], field)
                self.assertEqual(metadata["api_settings"]["max_tokens"], 512)

    def test_refusal_truncation_and_malformed_responses_fail_cleanly(self):
        values = [
            {"choices": [{"finish_reason": "stop", "message": {"refusal": "no", "content": ""}}]},
            {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
            {"choices": [{"finish_reason": "content_filter", "message": {"content": "{}"}}]},
            {"choices": []}, {"choices": [{"message": []}]},
        ]
        for value in values:
            with self.subTest(response=value), self.assertRaises(bc.BriefCheckError):
                self.call(value)

    def test_http_error_does_not_echo_provider_body_or_secret(self):
        error = urllib.error.HTTPError("https://provider.test", 401, "key=secret-not-for-logs", {}, io.BytesIO(b"secret-not-for-logs"))
        with mock.patch("briefcheck.open_http", side_effect=error):
            with self.assertRaises(bc.BriefCheckError) as caught:
                bc.call_api({"system": "JSON", "user": "input"}, "model", "secret-not-for-logs", "https://provider.test/v1", 20)
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("secret-not-for-logs", str(caught.exception))

    def test_insecure_or_credential_bearing_endpoints_rejected(self):
        for url in ["http://provider.test/v1", "https://u:p@provider.test/v1", "https://provider.test/v1?key=secret", "https://provider.test/v1/chat/completions"]:
            with self.subTest(url=url), self.assertRaises(bc.BriefCheckError):
                bc.endpoint(url)

    def test_redirects_cannot_forward_the_bearer_key_to_another_origin(self):
        self.assertIsNone(bc.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://other.test"))


class ConfigurationTests(unittest.TestCase):
    def configuration(self, environment=None, flags=()):
        args = bc.parser().parse_args(["run", "--ticker", "EXWIRE", "--docs", "docs", "--as-of", "2026-09-23", "--run", "unused-run", *flags])
        values = {"LLM_MODEL": "requested/model", "LLM_API_KEY": "synthetic-key"}
        values.update(environment or {})
        with mock.patch.dict(os.environ, values, clear=True):
            return bc.api_configuration(args)

    def test_defaults_preserve_bearer_json_object_and_optional_token_budget(self):
        settings, key = self.configuration()
        self.assertEqual(key, "synthetic-key")
        self.assertEqual(settings, {"requested_model": "requested/model", "base_url": "https://api.openai.com/v1", "endpoint": "https://api.openai.com/v1/chat/completions", "auth_mode": "bearer", "json_mode": "json_object", "token_parameter": "max_completion_tokens", "max_tokens": None, "timeout_seconds": 120})
        self.assertNotIn(key, json.dumps(settings))

    def test_environment_settings_are_resolved_and_anonymous_mode_discards_keys(self):
        settings, key = self.configuration({"LLM_MODEL": " routed/selector ", "LLM_BASE_URL": " https://provider.test/v1/ ", "LLM_AUTH_MODE": "none", "LLM_JSON_MODE": "prompt", "LLM_TOKEN_PARAMETER": "max_tokens", "LLM_MAX_TOKENS": "700", "LLM_TIMEOUT_SECONDS": "30.5", "OPENAI_API_KEY": "ambient-key"})
        self.assertEqual(key, "")
        self.assertEqual(settings, {"requested_model": "routed/selector", "base_url": "https://provider.test/v1", "endpoint": "https://provider.test/v1/chat/completions", "auth_mode": "none", "json_mode": "prompt", "token_parameter": "max_tokens", "max_tokens": 700, "timeout_seconds": 30.5})

    def test_explicit_cli_values_override_even_invalid_lower_priority_environment(self):
        settings, _ = self.configuration({"LLM_TIMEOUT_SECONDS": "invalid", "LLM_MAX_TOKENS": "invalid"}, ["--timeout", "120", "--max-tokens", "321"])
        self.assertEqual(settings["timeout_seconds"], 120)
        self.assertEqual(settings["max_tokens"], 321)

    def test_invalid_enums_are_rejected(self):
        for name, value in [("LLM_AUTH_MODE", "auto"), ("LLM_AUTH_MODE", ""), ("LLM_JSON_MODE", "json_schema"), ("LLM_TOKEN_PARAMETER", "max_output_tokens")]:
            with self.subTest(name=name, value=value), self.assertRaisesRegex(bc.BriefCheckError, name):
                self.configuration({name: value})

    def test_invalid_numeric_settings_are_rejected(self):
        for name, values in [("LLM_MAX_TOKENS", ["0", "-1", "1.5", "invalid", "NaN"]), ("LLM_TIMEOUT_SECONDS", ["0", "601", "NaN", "inf", "invalid", ""])]:
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaisesRegex(bc.BriefCheckError, name):
                    self.configuration({name: value})
        for flags in [["--timeout", "nan"], ["--timeout", "0"], ["--max-tokens", "0"]]:
            with self.subTest(flags=flags), self.assertRaises(bc.BriefCheckError):
                self.configuration(flags=flags)

    def test_key_requirement_and_precedence_follow_authentication_mode(self):
        with self.assertRaisesRegex(bc.BriefCheckError, "Bearer authentication requires"):
            self.configuration({"LLM_API_KEY": ""})
        _, key = self.configuration({"LLM_API_KEY": "", "OPENAI_API_KEY": "fallback-key"})
        self.assertEqual(key, "fallback-key")
        _, key = self.configuration({"OPENAI_API_KEY": "unused-fallback"})
        self.assertEqual(key, "synthetic-key")
        _, key = self.configuration({"LLM_AUTH_MODE": "none", "LLM_API_KEY": ""})
        self.assertEqual(key, "")
        with self.assertRaisesRegex(bc.BriefCheckError, "requires LLM_MODEL"):
            self.configuration({"LLM_AUTH_MODE": "none", "LLM_MODEL": " "})


class ApiWorkflowTests(Workspace):
    def arguments(self, name="api-run", version="v3"):
        return bc.parser().parse_args(["run", "--ticker", "EXWIRE", "--docs", str(self.docs), "--as-of", "2026-09-23", "--version", version, "--run", str(self.work / name)])

    def environment(self):
        return {"LLM_MODEL": "openrouter/free", "LLM_BASE_URL": "https://provider.test/v1", "LLM_AUTH_MODE": "none", "LLM_JSON_MODE": "prompt", "LLM_TOKEN_PARAMETER": "max_tokens", "LLM_MAX_TOKENS": "512", "LLM_TIMEOUT_SECONDS": "37.5", "LLM_API_KEY": "ambient-secret", "OPENAI_API_KEY": "other-ambient-secret"}

    def wire_response(self, content, model="provider/snapshot"):
        return ApiTests.response({"id": "synthetic-response-id", "model": model, "choices": [{"finish_reason": "stop", "message": {"content": content}}]})

    def test_three_stage_api_run_archives_effective_settings_and_reported_models(self):
        draft = self.brief()
        responses = [draft, self.audit(draft), draft]
        models = ["provider/draft-v1", "provider/audit-v2", "provider/revise-v3"]
        replies = [self.wire_response(bc.dumps(value), model) for value, model in zip(responses, models)]
        args = self.arguments()
        with mock.patch.dict(os.environ, self.environment(), clear=True), mock.patch("briefcheck.open_http", side_effect=replies) as send, contextlib.redirect_stdout(io.StringIO()):
            bc.api_run(args)
        run = Path(args.run)
        manifest = bc.read_json(run / "manifest.json")
        self.assertEqual(send.call_count, 3)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["api_settings"]["requested_model"], "openrouter/free")
        self.assertEqual(manifest["api_settings"]["endpoint"], "https://provider.test/v1/chat/completions")
        self.assertNotIn("ambient-secret", (run / "manifest.json").read_text())
        for call, stage, model in zip(send.call_args_list, manifest["stages"], models):
            request = call.args[0]
            payload = json.loads(request.data)
            archived = bc.read_json(run / stage["request_file"])
            self.assertFalse(request.has_header("Authorization"))
            self.assertNotIn("response_format", payload)
            self.assertEqual(payload["max_tokens"], 512)
            self.assertEqual(call.kwargs["timeout"], 37.5)
            self.assertEqual(payload["messages"], [{"role": "system", "content": archived["system"]}, {"role": "user", "content": archived["user"]}])
            self.assertIn("Return a single JSON object", archived["system"])
            self.assertEqual(stage["response_metadata"]["api_settings"], manifest["api_settings"])
            self.assertEqual(stage["response_metadata"]["reported_model"], model)
        rendered = (run / "report.html").read_text()
        self.assertIn("Requested model selector</strong><br>openrouter/free", rendered)
        self.assertIn("Reported model by stage", rendered)
        for stage, model in zip(("Draft", "Audit", "Revise"), models):
            self.assertIn(f"{stage}: {model}", rendered)
        self.assertNotIn("Model used</strong><br>openrouter/free", rendered)
        self.assertTrue(bc.verify_run(run)[-1]["ok"])

    def test_prompt_mode_still_rejects_invalid_json_schema_and_quotes_without_retry(self):
        bad_quote = self.brief()
        bad_quote["claims"][0]["evidence"][0]["quote"] = "This sentence was never in the source."
        invalid = [("```json\n{}\n```", "valid JSON object"), ('{"unexpected":true}', "missing fields"), (bc.dumps(bad_quote), "not an exact substring")]
        for index, (content, error) in enumerate(invalid):
            args = self.arguments(f"invalid-{index}")
            with self.subTest(error=error), mock.patch.dict(os.environ, self.environment(), clear=True), mock.patch("briefcheck.open_http", return_value=self.wire_response(content)) as send, contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(bc.BriefCheckError, "Response rejected and archived"):
                    bc.api_run(args)
            run = Path(args.run)
            self.assertEqual(send.call_count, 1)
            self.assertNotIn("response_format", json.loads(send.call_args.args[0].data))
            self.assertEqual((run / "rejected/01-draft.raw.txt").read_text(), content)
            self.assertIn(error, " ".join(bc.read_json(run / "rejected/01-draft.validation.json")["errors"]))
            self.assertEqual(bc.read_json(run / "manifest.json")["next_stage"], "draft")
            self.assertFalse((run / "01-draft.response.json").exists())

    def test_invalid_configuration_prevents_run_creation_and_network_calls(self):
        for index, changes in enumerate([{"LLM_AUTH_MODE": "auto"}, {"LLM_JSON_MODE": "invalid"}, {"LLM_TOKEN_PARAMETER": "invalid"}, {"LLM_MAX_TOKENS": "0"}, {"LLM_TIMEOUT_SECONDS": "nan"}, {"LLM_BASE_URL": "https://[invalid"}]):
            args = self.arguments(f"config-{index}")
            with self.subTest(changes=changes), mock.patch.dict(os.environ, self.environment() | changes, clear=True), mock.patch("briefcheck.open_http") as send:
                with self.assertRaises(bc.BriefCheckError):
                    bc.api_run(args)
                send.assert_not_called()
                self.assertFalse(Path(args.run).exists())

    def test_legacy_api_report_uses_selector_fallback_and_escapes_reported_model(self):
        run = self.prepare("v1")
        self.accept(run, self.brief())
        manifest, sources, draft, audit, final, validation = bc.verify_run(run)
        self.assertNotIn("api_settings", manifest)
        manifest["mode"] = "api"
        manifest["model_label"] = "routed/selector"
        manifest["stages"][0]["response_metadata"] = {"reported_model": "<b>provider/snapshot</b>"}
        rendered = report.render_report(manifest, sources, draft, audit, final, validation, cached=True)
        self.assertIn("Requested model selector</strong><br>routed/selector", rendered)
        self.assertIn("Draft: &lt;b&gt;provider/snapshot&lt;/b&gt;", rendered)
        self.assertNotIn("<b>provider/snapshot</b>", rendered)
        manifest["stages"][0]["response_metadata"] = {}
        rendered = report.render_report(manifest, sources, draft, audit, final, validation, cached=True)
        self.assertIn("Draft: Not reported by provider", rendered)


class RendererTests(unittest.TestCase):
    def test_html_source_markup_and_dangerous_links_stay_inert(self):
        rendered = report.markdown('<script>alert(1)</script> [click](javascript:alert(1)) **safe**')
        self.assertNotIn("<script>", rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("<strong>safe</strong>", rendered)
        self.assertIsNone(report.safe_url("javascript:alert(1)"))


if __name__ == "__main__":
    unittest.main()
