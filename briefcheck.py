#!/usr/bin/env python3
"""BriefCheck: draft, independently audit, and revise a cited research brief."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parent
VERSIONS = {"v1": ["draft"], "v2": ["draft", "audit", "revise"], "v3": ["draft", "audit", "revise"]}
HEADINGS = ["Snapshot", "Bull case", "Bear case", "Open questions", "Sources"]
SOURCE_PATTERN = r"S-[0-9a-f]{12}"
CITATION_RE = re.compile(r"\[(" + SOURCE_PATTERN + r")\]")
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_CORPUS_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_BRIEF_WORDS = 650


class BriefCheckError(Exception):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.write_text(dumps(value), encoding="utf-8")


def strict_json(data: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise BriefCheckError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def bad_constant(value: str) -> None:
        raise BriefCheckError("JSON cannot contain NaN or Infinity.")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=bad_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BriefCheckError("Response must be one valid JSON object, without Markdown fences.") from exc


def read_json(path: Path) -> Any:
    try:
        return strict_json(path.read_bytes())
    except OSError as exc:
        raise BriefCheckError(f"Cannot read required file: {path}") from exc


def parse_date(value: str) -> dt.date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BriefCheckError("Dates must be valid YYYY-MM-DD dates.") from exc


def metadata(raw: str) -> dict[str, str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return result
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if separator:
            key = key.strip().lower()
            if key in result:
                raise BriefCheckError(f"Duplicate frontmatter field: {key}")
            result[key] = value.strip().strip("\"'")
    raise BriefCheckError("Unclosed frontmatter. Each document must close its opening --- block.")


def load_sources(folder: Path, as_of: str) -> list[dict]:
    cutoff = parse_date(as_of)
    if not folder.is_dir():
        raise BriefCheckError(f"Document folder does not exist: {folder}")
    paths = sorted((p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in {".md", ".txt"} and p.name.lower() != "readme.md"), key=lambda p: p.relative_to(folder).as_posix())
    if not paths:
        raise BriefCheckError("No .md or .txt research documents found. README.md is excluded.")
    records, total, ids = [], 0, set()
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise BriefCheckError("Document symlinks outside the input folder are not accepted.")
        relative = path.relative_to(folder).as_posix()
        data = path.read_bytes()
        total += len(data)
        if len(data) > MAX_DOCUMENT_BYTES or total > MAX_CORPUS_BYTES:
            raise BriefCheckError("Corpus exceeds the explicit size limit (1 MiB/file, 4 MiB total); no document was silently truncated.")
        try:
            raw = data.decode("utf-8")
        except UnicodeError as exc:
            raise BriefCheckError(f"Research documents must be UTF-8: {relative}") from exc
        meta = metadata(raw)
        published = meta.get("published", "")
        try:
            published_date = parse_date(published)
            eligible = published_date <= cutoff
            exclusion = None if eligible else "Published after the requested research date."
        except BriefCheckError:
            eligible, exclusion = False, "Missing or invalid publication date; excluded to avoid undated evidence."
        source_id = "S-" + digest(relative.encode("utf-8"))[:12]
        if source_id in ids:
            raise BriefCheckError("Source ID collision. Rename one input file and prepare a new run.")
        ids.add(source_id)
        records.append({"source_id": source_id, "filename": relative, "sha256": digest(data), "metadata": meta, "published": published or None, "eligible": eligible, "exclusion_reason": exclusion, "raw": raw})
    if not any(s["eligible"] for s in records):
        raise BriefCheckError("No dated source is available on or before the research date.")
    return records


def schema(stage: str) -> dict:
    return read_json(ROOT / "schemas" / ("audit.json" if stage == "audit" else "brief.json"))


def validate_schema(value: Any, spec: dict, path: str = "response") -> list[str]:
    errors = []
    kinds = spec.get("type", [])
    kinds = [kinds] if isinstance(kinds, str) else kinds
    type_matches = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }
    if kinds and not any(type_matches.get(kind, False) for kind in kinds):
        return [f"{path}: expected {' or '.join(kinds)}"]
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path}: value is not an allowed enum member")
    if isinstance(value, dict):
        required = set(spec.get("required", []))
        missing = required - value.keys()
        if missing:
            errors.append(f"{path}: missing fields {', '.join(sorted(missing))}")
        properties = spec.get("properties", {})
        if spec.get("additionalProperties") is False:
            extra = value.keys() - properties.keys()
            if extra:
                errors.append(f"{path}: unknown fields {', '.join(sorted(extra))}")
        for key, child in properties.items():
            if key in value:
                errors.extend(validate_schema(value[key], child, f"{path}.{key}"))
    if isinstance(value, list):
        if len(value) < spec.get("minItems", 0):
            errors.append(f"{path}: too few items")
        for index, item in enumerate(value):
            errors.extend(validate_schema(item, spec.get("items", {}), f"{path}[{index}]"))
    if isinstance(value, str):
        if len(value) < spec.get("minLength", 0):
            errors.append(f"{path}: string is too short")
        if spec.get("pattern") and not re.search(spec["pattern"], value):
            errors.append(f"{path}: string does not match the required pattern")
    return errors


def check_evidence(evidence: dict, sources: dict, label: str, errors: list) -> None:
    source = sources.get(evidence["source_id"])
    if source is None:
        errors.append(f"{label}: unknown source ID")
    elif not source["eligible"]:
        errors.append(f"{label}: source is unavailable on the research date")
    else:
        if evidence["quote"] not in source["raw"]:
            errors.append(f"{label}: quote is not an exact substring of the cited raw source")
        if evidence["published"] != source["published"]:
            errors.append(f"{label}: publication date differs from the cited source metadata")


def sections(markdown: str) -> dict[str, str]:
    found = list(re.finditer(r"^## (Snapshot|Bull case|Bear case|Open questions|Sources)\s*$", markdown, re.M))
    return {m.group(1): markdown[m.end(): found[i + 1].start() if i + 1 < len(found) else len(markdown)].strip() for i, m in enumerate(found)}


def validate_brief(response: dict, sources: list[dict], as_of: str, version: str, audit: dict | None = None, expected_ticker: str | None = None) -> dict:
    errors = validate_schema(response, schema("draft"))
    warnings = []
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    by_source = {s["source_id"]: s for s in sources}
    text = response["brief_markdown"]
    title = next((line for line in text.splitlines() if line.startswith("# ")), "")
    if expected_ticker and not re.search(r"(?<![A-Za-z0-9&_.-])" + re.escape(expected_ticker) + r"(?![A-Za-z0-9&_.-])", title, re.I):
        errors.append("Brief title must contain the requested ticker.")
    found = re.findall(r"^## (.+?)\s*$", text, re.M)
    if found != HEADINGS:
        errors.append("Brief must contain exactly the five required ## headings, in the requested order.")
    if as_of not in text:
        errors.append("Brief must display the requested as-of date as YYYY-MM-DD.")
    if len(text.split()) > MAX_BRIEF_WORDS:
        errors.append(f"Brief exceeds {MAX_BRIEF_WORDS} words including sources.")
    for source_id in set(CITATION_RE.findall(text)):
        if source_id not in by_source or not by_source[source_id]["eligible"]:
            errors.append(f"Brief cites an unknown or date-excluded source: {source_id}")
    claim_ids, mapped = set(), set()
    excluded_entities = {r["source_id"] for r in (audit or {}).get("document_reviews", []) if r["relevance"] == "different_entity"}
    parts = sections(text)
    body = "\n".join(parts.get(h, "") for h in HEADINGS[:-1])
    for claim in response["claims"]:
        label = claim["claim_id"]
        if label in claim_ids:
            errors.append(f"Duplicate claim ID: {label}")
        claim_ids.add(label)
        if claim["text"] not in body:
            errors.append(f"{label}: claim text must occur verbatim in the brief's first four sections.")
        if claim["kind"] != "question" and not claim["evidence"]:
            errors.append(f"{label}: a non-question claim requires at least one source passage.")
        evidence_ids = {e["source_id"] for e in claim["evidence"]}
        cited_ids = set(CITATION_RE.findall(claim["text"]))
        if evidence_ids != cited_ids:
            errors.append(f"{label}: inline citations and claim evidence source IDs must match exactly.")
        mapped |= evidence_ids
        for index, evidence in enumerate(claim["evidence"]):
            check_evidence(evidence, by_source, f"{label}.evidence[{index}]", errors)
        period = claim["period"]
        if period and re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
            try:
                period_date = parse_date(period)
                if period_date > parse_date(as_of) and claim["kind"] == "fact":
                    errors.append(f"{label}: a future period cannot be labelled a reported fact.")
            except BriefCheckError:
                errors.append(f"{label}: period is an invalid ISO date.")
        if version == "v3":
            if claim["kind"] in {"fact", "management_view"} and claim["entity"] != response["entity_name"]:
                errors.append(f"{label}: fact/management entity differs from the response entity.")
            if evidence_ids & excluded_entities:
                errors.append(f"{label}: revision uses a source the auditor identified as a different entity.")
            if claim["kind"] == "management_view" and not re.search(r"\b(management|company|CFO|CEO|chief financial officer|chief executive officer|expects?|expected|guidance|plans?|planned|according|said|intends?|targets?|scheduled)\b", claim["text"], re.I):
                errors.append(f"{label}: management view needs explicit attribution or expectation wording.")
    if set(CITATION_RE.findall(body)) - mapped:
        errors.append("A citation in the brief body has no corresponding claim-map evidence.")
    source_section = parts.get("Sources", "")
    for source_id in mapped:
        if f"[{source_id}]" not in source_section:
            errors.append(f"The Sources section omits a claim's source: {source_id}")
    if version == "v3":
        snapshot_lines = [line for line in parts.get("Snapshot", "").splitlines() if line.strip()]
        if len(snapshot_lines) not in {3, 4}:
            errors.append("v3 Snapshot must contain 3–4 nonempty prose lines.")
        registry_ids = CITATION_RE.findall(source_section)
        if len(registry_ids) != len(set(registry_ids)):
            errors.append("v3 Sources must list each source ID exactly once.")
        if set(registry_ids) != mapped:
            errors.append("v3 Sources registry must contain exactly the source IDs used in the body claim map.")
        for line in source_section.splitlines():
            line_ids = CITATION_RE.findall(line)
            if not line.strip():
                continue
            if len(line_ids) != 1:
                errors.append("v3 Sources requires one source ID and its metadata per nonempty line.")
                continue
            source = by_source.get(line_ids[0])
            if source and source["eligible"]:
                for field, expected in (("filename", source["filename"]), ("publication date", source["published"]), ("URL", source["metadata"].get("url", ""))):
                    if expected and expected not in line:
                        errors.append(f"v3 source registry {source['source_id']}: exact {field} is missing or altered.")
        uncovered = body
        for claim in sorted(response["claims"], key=lambda c: len(c["text"]), reverse=True):
            uncovered = uncovered.replace(claim["text"], "")
        uncovered = re.sub(r"[\s*\-+>#]", "", uncovered)
        if uncovered:
            errors.append("v3 requires every body paragraph/bullet to be covered by exact claim-map text; unmapped text remains.")
    words = len(text.split())
    if words > 550:
        warnings.append("Brief is above the preferred 400–550-word range; the hard limit is 650 including sources.")
    warnings.append("Passing checks establishes shape, citation identity, exact quotation provenance and selected consistency rules; it does not establish entailment or factual truth.")
    if audit:
        warnings.append("The final revision is not subjected to a second model audit. One revision is the deliberate bound.")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "brief_words": words, "mapped_claims": len(response["claims"]), "cited_sources": len(mapped)}


def validate_audit(response: dict, draft: dict, sources: list[dict]) -> dict:
    errors = validate_schema(response, schema("audit"))
    if errors:
        return {"ok": False, "errors": errors, "warnings": []}
    by_source = {s["source_id"]: s for s in sources}
    expected_claims = {c["claim_id"] for c in draft["claims"]}
    observed_claims = [c["claim_id"] for c in response["claim_reviews"]]
    if set(observed_claims) != expected_claims or len(set(observed_claims)) != len(observed_claims):
        errors.append("Audit must review every draft claim exactly once, using the original claim IDs.")
    expected_sources = {s["source_id"] for s in sources if s["eligible"]}
    observed_sources = [r["source_id"] for r in response["document_reviews"]]
    if set(observed_sources) != expected_sources or len(set(observed_sources)) != len(observed_sources):
        errors.append("Audit must review every date-eligible source exactly once.")
    for review in response["document_reviews"]:
        source = by_source.get(review["source_id"])
        if source is None or review["quote"] not in source["raw"]:
            errors.append(f"Document review {review['source_id']}: passage is not an exact source quote.")
    for review in response["claim_reviews"]:
        if review["verdict"] != "supported" and not review["correction"].strip():
            errors.append(f"{review['claim_id']}: an adverse verdict requires a scoped correction.")
        for index, evidence in enumerate(review["evidence"]):
            check_evidence(evidence, by_source, f"audit.{review['claim_id']}.evidence[{index}]", errors)
    return {"ok": not errors, "errors": errors, "warnings": ["Audit verdicts are model judgments, not verified facts or confidence scores."]}


def load_state(run: Path) -> tuple[dict, list[dict]]:
    manifest = read_json(run / "manifest.json")
    sources = read_json(run / "sources.json")
    if manifest.get("sources_sha256") != digest((run / "sources.json").read_bytes()):
        raise BriefCheckError("Source manifest integrity check failed.")
    for source in sources:
        snapshot = run / "source_snapshots" / source["filename"]
        if not snapshot.is_file() or digest(snapshot.read_bytes()) != source["sha256"]:
            raise BriefCheckError("A source snapshot changed or is missing.")
        if digest(source["raw"].encode("utf-8")) != source["sha256"]:
            raise BriefCheckError("Archived source text differs from its original hash.")
    return manifest, sources


def stage_record(manifest: dict, stage: str) -> dict:
    return next(r for r in manifest["stages"] if r["stage"] == stage)


def stage_output(run: Path, manifest: dict, stage: str) -> dict:
    record = stage_record(manifest, stage)
    data = (run / record["response_file"]).read_bytes()
    if digest(data) != record["response_sha256"]:
        raise BriefCheckError(f"Archived {stage} response changed.")
    return strict_json(data)


def write_request(run: Path, manifest: dict, sources: list[dict], stage: str) -> None:
    index = manifest["sequence"].index(stage) + 1
    prompt_file = ROOT / "prompts" / manifest["version"] / f"{stage}.md"
    response_schema = schema(stage)
    system = prompt_file.read_text(encoding="utf-8").strip() + "\n\nReturn a single JSON object that follows this schema exactly. JSON is required, without code fences.\n" + dumps(response_schema)
    payload = {
        "task": {"ticker": manifest["ticker"], "as_of": manifest["as_of"], "audience": "Retail investor", "preferred_words_including_sources": "400–550", "maximum_words_including_sources": MAX_BRIEF_WORDS},
        "source_inventory": [{k: v for k, v in s.items() if k != "raw"} for s in sources],
        "documents": [{"source_id": s["source_id"], "filename": s["filename"], "published": s["published"], "raw": s["raw"]} for s in sources if s["eligible"]],
    }
    if stage in {"audit", "revise"}:
        payload["draft"] = stage_output(run, manifest, "draft")
    if stage == "revise":
        payload["audit"] = stage_output(run, manifest, "audit")
    request = {"format": "briefcheck.request.v1", "stage": stage, "version": manifest["version"], "context_policy": "Start a fresh model conversation for this stage. Supply only this system message and this user message.", "system": system, "user": dumps(payload), "response_schema": response_schema}
    filename = f"{index:02d}-{stage}.request.json"
    write_json(run / filename, request)
    (run / "request.json").write_bytes((run / filename).read_bytes())
    readable = f"# BriefCheck · {manifest['version']} · {stage}\n\nUse a fresh model conversation for this stage. Return the raw JSON reply in a file; do not edit it by hand.\n\n## System\n\n{system}\n\n## User\n\n```json\n{request['user']}```\n"
    (run / f"{index:02d}-{stage}.request.md").write_text(readable, encoding="utf-8")
    (run / "request.md").write_text(readable, encoding="utf-8")
    manifest["stages"].append({"stage": stage, "request_file": filename, "request_sha256": digest((run / filename).read_bytes()), "prompt_file": str(prompt_file.relative_to(ROOT)), "prompt_sha256": digest(prompt_file.read_bytes()), "status": "pending"})
    manifest["next_stage"] = stage
    write_json(run / "manifest.json", manifest)


def prepare(args: argparse.Namespace, mode: str = "file_handoff", api_config: dict | None = None) -> Path:
    if mode == "api" and api_config is None:
        api_config, _ = api_configuration(args)
    run = Path(args.run)
    if run.exists() and any(run.iterdir()):
        raise BriefCheckError("Run directory already has files. Choose a new run directory; archived runs are never overwritten.")
    parse_date(args.as_of)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9&_.-]{0,39}", args.ticker):
        raise BriefCheckError("Ticker must use 1–40 letters, digits, &, _, . or -.")
    sources = load_sources(Path(args.docs), args.as_of)
    run.mkdir(parents=True, exist_ok=True)
    write_json(run / "sources.json", sources)
    for source in sources:
        target = run / "source_snapshots" / source["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source["raw"].encode("utf-8"))
    model_label = args.model_label if mode == "file_handoff" else api_config["requested_model"]
    model_settings = "Not exposed by file handoff; no claim of a pinned backend snapshot."
    if mode == "api":
        json_label = "Provider JSON object mode" if api_config["json_mode"] == "json_object" else "Prompt-requested JSON"
        model_settings = f"{json_label}; local JSON, schema and quote checks enforced; no temperature supplied; other provider defaults unless explicitly configured."
    manifest = {"format": "briefcheck.run.v1", "created_at": now(), "status": "pending", "mode": mode, "model_label": model_label, "model_settings": model_settings, "ticker": args.ticker, "as_of": args.as_of, "version": args.version, "sequence": VERSIONS[args.version], "stages": [], "sources_sha256": digest((run / "sources.json").read_bytes()), "code_sha256": digest(Path(__file__).read_bytes()), "automatic_revision_limit": 0 if args.version == "v1" else 1, "semantic_final_audit": "not_performed_after_revision" if args.version != "v1" else "no_audit_in_baseline"}
    if mode == "api":
        manifest["api_settings"] = dict(api_config)
    write_request(run, manifest, sources, "draft")
    print(f"Prepared {args.version}: {run / 'request.json'}")
    return run


def record_rejection(run: Path, stage: str, data: bytes, report: dict) -> None:
    rejected = run / "rejected"
    rejected.mkdir(exist_ok=True)
    number = len(list(rejected.glob("*.raw.txt"))) + 1
    (rejected / f"{number:02d}-{stage}.raw.txt").write_bytes(data)
    write_json(rejected / f"{number:02d}-{stage}.validation.json", report)


def accept_response(run: Path, data: bytes, response_meta: dict | None = None) -> dict:
    manifest, sources = load_state(run)
    if manifest["status"] != "pending":
        raise BriefCheckError("Run is already complete. Prepare a new run for another model output.")
    transport = (response_meta or {}).get("transport")
    if manifest["mode"] == "api" and transport != "https_api":
        raise BriefCheckError("An API run accepts only responses returned by the API runner. Prepare a separate file-handoff run for manual captures.")
    if manifest["mode"] == "file_handoff" and transport not in {None, "file_handoff"}:
        raise BriefCheckError("A file-handoff run cannot accept API transport metadata.")
    stage = manifest["next_stage"]
    record = stage_record(manifest, stage)
    if digest((run / record["request_file"]).read_bytes()) != record["request_sha256"] or (run / "request.json").read_bytes() != (run / record["request_file"]).read_bytes():
        raise BriefCheckError("Pending request changed. Prepare a new run rather than rewriting an archived prompt.")
    try:
        if len(data) > MAX_RESPONSE_BYTES:
            raise BriefCheckError("Model response exceeds 4 MiB; it was not silently truncated.")
        response = strict_json(data)
        if stage == "audit":
            report = validate_audit(response, stage_output(run, manifest, "draft"), sources)
        else:
            audit = stage_output(run, manifest, "audit") if stage == "revise" else None
            report = validate_brief(response, sources, manifest["as_of"], manifest["version"], audit, manifest["ticker"])
    except BriefCheckError as exc:
        report = {"ok": False, "errors": [str(exc)], "warnings": []}
    if not report["ok"]:
        record_rejection(run, stage, data, report)
        raise BriefCheckError("Response rejected and archived; current stage is still pending:\n" + "\n".join(report["errors"]))
    index = manifest["sequence"].index(stage) + 1
    filename = f"{index:02d}-{stage}.response.json"
    (run / filename).write_bytes(data)
    write_json(run / f"{index:02d}-{stage}.validation.json", report)
    record.update({"status": "accepted", "response_file": filename, "response_sha256": digest(data), "accepted_at": now(), "response_metadata": response_meta or {"transport": "file_handoff", "backend_snapshot": "not exposed", "generation_elapsed_seconds": None}})
    write_json(run / "manifest.json", manifest)
    if index < len(manifest["sequence"]):
        write_request(run, manifest, sources, manifest["sequence"][index])
        print(f"Accepted {stage}; next stage: {manifest['sequence'][index]} ({run / 'request.json'})")
    else:
        manifest["status"], manifest["next_stage"], manifest["completed_at"] = "complete", None, now()
        write_json(run / "manifest.json", manifest)
        (run / "brief.md").write_text(response["brief_markdown"], encoding="utf-8")
        write_json(run / "claim_map.json", response["claims"])
        write_json(run / "validation.json", report)
        from report import render_report
        draft = stage_output(run, manifest, "draft")
        audit = stage_output(run, manifest, "audit") if "audit" in manifest["sequence"] else None
        (run / "report.html").write_text(render_report(manifest, sources, draft, audit, response, report, cached=False), encoding="utf-8")
        (run / "request.json").unlink()
        (run / "request.md").unlink()
        print(f"Complete: {run / 'brief.md'} and {run / 'report.html'}")
    return report


def verify_run(run: Path) -> tuple[dict, list[dict], dict, dict | None, dict, dict]:
    manifest, sources = load_state(run)
    if manifest.get("status") != "complete":
        raise BriefCheckError("Only a completed run can be replayed or validated.")
    outputs = {}
    for record in manifest["stages"]:
        request_file = run / record["request_file"]
        if not request_file.is_file() or digest(request_file.read_bytes()) != record["request_sha256"]:
            raise BriefCheckError("An archived request changed or is missing.")
        expected_transport = "https_api" if manifest["mode"] == "api" else "file_handoff"
        if record.get("response_metadata", {}).get("transport") != expected_transport:
            raise BriefCheckError("Archived response transport does not match the run mode.")
        outputs[record["stage"]] = stage_output(run, manifest, record["stage"])
    draft_report = validate_brief(outputs["draft"], sources, manifest["as_of"], manifest["version"], expected_ticker=manifest["ticker"])
    if not draft_report["ok"]:
        raise BriefCheckError("Archived draft no longer passes validation: " + "; ".join(draft_report["errors"]))
    audit = outputs.get("audit")
    if audit:
        audit_report = validate_audit(audit, outputs["draft"], sources)
        if not audit_report["ok"]:
            raise BriefCheckError("Archived audit no longer passes validation: " + "; ".join(audit_report["errors"]))
    final = outputs.get("revise", outputs["draft"])
    report = validate_brief(final, sources, manifest["as_of"], manifest["version"], audit, manifest["ticker"])
    if not report["ok"]:
        raise BriefCheckError("Archived final no longer passes validation: " + "; ".join(report["errors"]))
    if (run / "brief.md").read_bytes() != final["brief_markdown"].encode("utf-8"):
        raise BriefCheckError("brief.md differs from the model's archived final JSON. Manual edits must be disclosed separately.")
    return manifest, sources, outputs["draft"], audit, final, report


def replay(run: Path, out: Path) -> None:
    manifest, sources, draft, audit, final, report = verify_run(run)
    if out.exists() and any(out.iterdir()):
        raise BriefCheckError("Replay output directory is not empty. Choose a fresh directory.")
    out.mkdir(parents=True, exist_ok=True)
    from report import render_report
    (out / "report.html").write_text(render_report(manifest, sources, draft, audit, final, report, cached=True), encoding="utf-8")
    (out / "brief.md").write_text(final["brief_markdown"], encoding="utf-8")
    write_json(out / "replay.json", {"mode": "cached_replay", "generated_at": now(), "origin_model_label": manifest["model_label"], "origin_manifest_sha256": digest((run / "manifest.json").read_bytes()), "new_model_calls": 0, "validation": report})
    print(f"Cached replay verified. No model call was made: {out / 'report.html'}")


def endpoint(base: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(base.strip())
        parsed.port  # Reject malformed or out-of-range ports before preparing a run.
    except ValueError:
        raise BriefCheckError("LLM_BASE_URL must be a valid HTTPS base URL.") from None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BriefCheckError("LLM_BASE_URL must be an HTTPS base URL without credentials, query strings or fragments.")
    if parsed.path.rstrip("/").endswith("/chat/completions"):
        raise BriefCheckError("LLM_BASE_URL should end at the API base (for example /v1), before /chat/completions.")
    return base.strip().rstrip("/") + "/chat/completions"


def effective_api_settings(model: str, base: str, timeout: float, max_tokens: int | None, auth_mode: str, json_mode: str, token_parameter: str, reasoning_effort: str | None = None) -> dict:
    for name, value, allowed in (
        ("LLM_AUTH_MODE", auth_mode, ("bearer", "none")),
        ("LLM_JSON_MODE", json_mode, ("json_object", "prompt")),
        ("LLM_TOKEN_PARAMETER", token_parameter, ("max_completion_tokens", "max_tokens")),
    ):
        if value not in allowed:
            raise BriefCheckError(f"{name} must be one of: {', '.join(allowed)}.")
    if not model.strip():
        raise BriefCheckError("API mode requires LLM_MODEL.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 600:
        raise BriefCheckError("LLM_TIMEOUT_SECONDS or --timeout must be between 1 and 600 seconds.")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1):
        raise BriefCheckError("LLM_MAX_TOKENS or --max-tokens must be a positive integer when supplied.")
    if reasoning_effort not in (None, "none", "minimal", "low", "medium", "high"):
        raise BriefCheckError("LLM_REASONING_EFFORT must be none, minimal, low, medium or high.")
    url = endpoint(base)
    return {**({"reasoning_effort": reasoning_effort} if reasoning_effort else {}), "requested_model": model.strip(), "base_url": base.strip().rstrip("/"), "endpoint": url, "auth_mode": auth_mode, "json_mode": json_mode, "token_parameter": token_parameter, "max_tokens": max_tokens, "timeout_seconds": timeout}


def api_configuration(args: argparse.Namespace) -> tuple[dict, str]:
    timeout_value = getattr(args, "timeout", None)
    if timeout_value is None:
        timeout_value = os.environ.get("LLM_TIMEOUT_SECONDS", "120")
    try:
        timeout = float(str(timeout_value).strip())
    except ValueError:
        raise BriefCheckError("LLM_TIMEOUT_SECONDS or --timeout must be a number between 1 and 600 seconds.") from None
    token_value = getattr(args, "max_tokens", None)
    if token_value is None:
        token_value = os.environ.get("LLM_MAX_TOKENS", "")
    try:
        max_tokens = int(str(token_value).strip()) if str(token_value).strip() else None
    except ValueError:
        raise BriefCheckError("LLM_MAX_TOKENS or --max-tokens must be a positive integer when supplied.") from None
    settings = effective_api_settings(
        os.environ.get("LLM_MODEL", ""), os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        timeout, max_tokens, os.environ.get("LLM_AUTH_MODE", "bearer").strip(),
        os.environ.get("LLM_JSON_MODE", "json_object").strip(),
        os.environ.get("LLM_TOKEN_PARAMETER", "max_completion_tokens").strip(),
        os.environ.get("LLM_REASONING_EFFORT", "").strip() or None,
    )
    key = ""
    if settings["auth_mode"] == "bearer":
        key = os.environ.get("LLM_API_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise BriefCheckError("Bearer authentication requires LLM_API_KEY (or OPENAI_API_KEY). Use LLM_AUTH_MODE=none only for a provider that permits anonymous requests, or prepare/accept for file handoff.")
    return settings, key


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_http(request: urllib.request.Request, timeout: float):
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout)


def call_api(request: dict, model: str, api_key: str, base: str, timeout: float, max_tokens: int | None = None, *, auth_mode: str = "bearer", json_mode: str = "json_object", token_parameter: str = "max_completion_tokens", reasoning_effort: str | None = None) -> tuple[bytes, dict]:
    settings = effective_api_settings(model, base, timeout, max_tokens, auth_mode, json_mode, token_parameter, reasoning_effort)
    payload = {"model": settings["requested_model"], "messages": [{"role": "system", "content": request["system"]}, {"role": "user", "content": request["user"]}]}
    if json_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        payload[token_parameter] = max_tokens
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    headers = {"Content-Type": "application/json", "User-Agent": "BriefCheck/1.1"}
    if auth_mode == "bearer":
        if not api_key:
            raise BriefCheckError("Bearer authentication requires an API key.")
        headers["Authorization"] = "Bearer " + api_key
    http_request = urllib.request.Request(settings["endpoint"], data=dumps(payload).encode("utf-8"), headers=headers, method="POST")
    started = time.monotonic()
    try:
        with open_http(http_request, timeout=timeout) as response:
            wire = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        descriptions = {401: "Check the API key." if auth_mode == "bearer" else "Check whether the provider permits anonymous requests.", 403: "The provider denied this request.", 429: "The provider rate limit or account quota was reached."}
        raise BriefCheckError(f"Model API returned HTTP {exc.code}. {descriptions.get(exc.code, 'Check endpoint, model support and account access.')} Response bodies and credentials are not logged.") from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        raise BriefCheckError("Could not reach the model API, or the request timed out. The pending request is preserved; credentials are not logged.") from None
    if len(wire) > MAX_RESPONSE_BYTES:
        raise BriefCheckError("API response exceeded 4 MiB; it was not silently truncated.")
    result = strict_json(wire)
    try:
        choice = result["choices"][0]
        message = choice["message"]
        if message.get("refusal"):
            raise BriefCheckError("The model refused the request. No research brief was accepted.")
        finish = choice.get("finish_reason")
        if finish == "length":
            raise BriefCheckError("Model output was truncated (finish_reason=length). Increase the output budget and start a new run.")
        if finish != "stop":
            raise BriefCheckError("Model did not finish with a normal text response; no output was accepted.")
        content = message["content"]
        if not isinstance(content, str) or not content.strip():
            raise BriefCheckError("Model response did not contain a nonempty JSON text message.")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise BriefCheckError("Unexpected API response shape. This runner requires the Chat Completions JSON response contract.") from None
    return content.encode("utf-8"), {"transport": "https_api", "reported_model": result.get("model"), "response_id": result.get("id"), "finish_reason": finish, "usage": result.get("usage"), "generation_elapsed_seconds": round(time.monotonic() - started, 3), "temperature_sent": False, "api_settings": settings}


def api_run(args: argparse.Namespace) -> None:
    settings, key = api_configuration(args)
    run = prepare(args, mode="api", api_config=settings)
    while read_json(run / "manifest.json")["status"] == "pending":
        request = read_json(run / "request.json")
        print(f"Calling model for {request['stage']} in a fresh context…")
        data, meta = call_api(request, settings["requested_model"], key, settings["base_url"], settings["timeout_seconds"], settings["max_tokens"], auth_mode=settings["auth_mode"], json_mode=settings["json_mode"], token_parameter=settings["token_parameter"], reasoning_effort=settings.get("reasoning_effort"))
        accept_response(run, data, meta)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="BriefCheck: one draft, an independent audit, one revision.")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run"):
        p = sub.add_parser(name, help="Prepare a file-handoff run" if name == "prepare" else "Run through an OpenAI-compatible HTTPS API")
        p.add_argument("--ticker", required=True)
        p.add_argument("--docs", required=True)
        p.add_argument("--as-of", required=True)
        p.add_argument("--version", choices=VERSIONS, default="v3")
        p.add_argument("--run", required=True)
        p.add_argument("--model-label", required=name == "prepare", default="")
        if name == "run":
            p.add_argument("--timeout", type=float, help="Override LLM_TIMEOUT_SECONDS (default: 120; range: 1–600)")
            p.add_argument("--max-tokens", type=int, help="Override optional LLM_MAX_TOKENS")
    p = sub.add_parser("accept", help="Validate and archive one unmodified model JSON response")
    p.add_argument("--run", required=True)
    p.add_argument("--response", required=True)
    p = sub.add_parser("replay", help="Validate and render archived outputs without a model call")
    p.add_argument("--run", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("validate", help="Validate a completed run and its provenance")
    p.add_argument("--run", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "run":
            api_run(args)
        elif args.command == "accept":
            accept_response(Path(args.run), Path(args.response).read_bytes())
        elif args.command == "replay":
            replay(Path(args.run), Path(args.out))
        else:
            report = verify_run(Path(args.run))[-1]
            print(dumps(report), end="")
        return 0
    except (BriefCheckError, OSError) as exc:
        print(f"BriefCheck: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
