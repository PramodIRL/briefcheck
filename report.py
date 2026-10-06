"""Self-contained, escaped HTML renderer. No Markdown dependency or remote assets."""

from __future__ import annotations

import difflib
import html
import re
import urllib.parse


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def safe_url(value: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username and not parsed.password else None


def inline(text: str) -> str:
    pattern = re.compile(r"(\[S-[0-9a-f]{12}\]|\*\*[^*]+\*\*|`[^`]+`|\[[^\]\n]+\]\([^\)\n]+\))")
    output, previous = [], 0
    for match in pattern.finditer(text):
        output.append(escape(text[previous:match.start()]))
        token = match.group()
        if re.fullmatch(r"\[S-[0-9a-f]{12}\]", token):
            source_id = token[1:-1]
            output.append(f'<a class="citation" href="#source-{source_id}" data-source="{source_id}">{escape(token)}</a>')
        elif token.startswith("**"):
            output.append(f"<strong>{escape(token[2:-2])}</strong>")
        elif token.startswith("`"):
            output.append(f"<code>{escape(token[1:-1])}</code>")
        else:
            label, target = re.fullmatch(r"\[([^\]]+)\]\(([^\)]+)\)", token).groups()
            url = safe_url(target)
            output.append(f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>' if url else escape(label))
        previous = match.end()
    output.append(escape(text[previous:]))
    return "".join(output)


def markdown(text: str) -> str:
    result, in_list = [], False
    for line in text.splitlines():
        is_list = bool(re.match(r"^\s*[-*+]\s+", line))
        if in_list and not is_list:
            result.append("</ul>")
            in_list = False
        if not line.strip():
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            level = min(len(heading[1]) + 1, 4)
            result.append(f"<h{level}>{inline(heading[2])}</h{level}>")
        elif is_list:
            if not in_list:
                result.append("<ul>")
                in_list = True
            result.append("<li>" + inline(re.sub(r"^\s*[-*+]\s+", "", line)) + "</li>")
        else:
            result.append("<p>" + inline(line) + "</p>")
    if in_list:
        result.append("</ul>")
    return "\n".join(result)


def evidence_cards(items: list[dict]) -> str:
    return "".join(f'<div class="evidence"><a class="source-jump" href="#source-{escape(e["source_id"])}" data-source="{escape(e["source_id"])}">{escape(e["source_id"])}</a><span class="tiny">Published {escape(e["published"])}</span><blockquote>{escape(e["quote"])}</blockquote></div>' for e in items)


def render_report(manifest: dict, sources: list[dict], draft: dict, audit: dict | None, final: dict, validation: dict, cached: bool) -> str:
    mode = "Cached replay · no new model call" if cached else ("Captured model responses · manual file handoff" if manifest["mode"] == "file_handoff" else "Generated through the model API")
    count = len([s for s in sources if s["eligible"]])
    finding_count = sum(c["verdict"] != "supported" for c in audit["claim_reviews"]) if audit else 0
    body = markdown(final["brief_markdown"])
    stages = "".join(f'<span class="stage"><i aria-hidden="true">✓</i>{escape(s)}</span>' for s in manifest["sequence"])
    claims = "".join(f'<details class="claim"><summary><span class="pill">{escape(c["claim_id"])}</span><span>{escape(c["text"])}</span></summary><div class="detail-inner"><p class="tiny">{escape(c["kind"].replace("_", " "))} · Entity: {escape(c["entity"])} · Period: {escape(c["period"] or "not specified")}</p>{evidence_cards(c["evidence"]) or "<p>Pure open question; no asserted fact is mapped.</p>"}</div></details>' for c in final["claims"])
    source_reviews = {r["source_id"]: r for r in audit["document_reviews"]} if audit else {}
    source_blocks = []
    for source in sources:
        review = source_reviews.get(source["source_id"])
        relevance = review["relevance"].replace("_", " ") if review else ("available to baseline" if source["eligible"] else "date excluded")
        reason = review["reason"] if review else (source["exclusion_reason"] or "No independent audit in the single-pass baseline.")
        url = safe_url(source["metadata"].get("url", ""))
        url_link = f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">Supplied URL ↗</a>' if url else "No valid HTTP(S) URL supplied"
        source_blocks.append(f'<details class="source" id="source-{escape(source["source_id"])}"><summary><span class="source-title">{escape(source["filename"])}</span><span class="pill neutral">{escape(relevance)}</span></summary><div class="detail-inner"><dl class="source-meta"><div><dt>ID</dt><dd>{escape(source["source_id"])}</dd></div><div><dt>Published</dt><dd>{escape(source["published"] or "unknown")}</dd></div><div><dt>Supplied source</dt><dd>{escape(source["metadata"].get("source", "unknown"))}</dd></div><div><dt>Reference</dt><dd>{url_link}</dd></div></dl><p>{escape(reason)}</p><p class="hash">SHA-256 {escape(source["sha256"])}</p><pre class="raw">{escape(source["raw"])}</pre></div></details>')
    review_rows = []
    if audit:
        original_claims = {c["claim_id"]: c["text"] for c in draft["claims"]}
        for item in audit["claim_reviews"]:
            review_rows.append(f'<details class="claim"><summary><span class="pill {"good" if item["verdict"] == "supported" else "amber"}">{escape(item["verdict"])}</span><span>{escape(item["claim_id"])} · {escape(original_claims[item["claim_id"]])}</span></summary><div class="detail-inner"><p>{escape(item["rationale"])}</p><p class="tiny">Checks: {escape(", ".join(item["issues"]))}</p>{"<p><strong>Correction:</strong> " + escape(item["correction"]) + "</p>" if item["correction"] else ""}{evidence_cards(item["evidence"])}</div></details>')
        review_intro = f'<p class="lead-small">{escape(audit["summary"])}</p><h3>Revision instructions</h3><ul>{"".join("<li>" + escape(i) + "</li>" for i in audit["revision_instructions"]) or "<li>No specific correction requested.</li>"}</ul>'
        limitations = audit["remaining_limitations"]
    else:
        review_intro = '<div class="empty"><h3>Single-pass baseline</h3><p>Version 1 deliberately has no critic stage. Its original generation and final brief are identical. Structural and quotation checks still run.</p></div>'
        limitations = ["There is no independent model audit in this baseline."]
    limitations = limitations + validation["warnings"]
    changes = list(difflib.ndiff(draft["brief_markdown"].splitlines(), final["brief_markdown"].splitlines()))
    diff_rows = "\n".join(f'<span class="diff-{ "add" if line.startswith("+ ") else "remove" if line.startswith("- ") else "same" }">{escape(line)}</span>' for line in changes if not line.startswith("? "))
    if manifest["mode"] == "api":
        selector = manifest.get("api_settings", {}).get("requested_model", manifest["model_label"])
        reported_models = "".join(f'<li>{escape(record["stage"].capitalize())}: {escape(record.get("response_metadata", {}).get("reported_model") or "Not reported by provider")}</li>' for record in manifest["stages"])
        model_details = f'<p class="subtle"><strong>Requested model selector</strong><br>{escape(selector)}</p><div class="subtle"><strong>Reported model by stage</strong><ul>{reported_models}</ul></div>'
    else:
        model_details = f'<p class="subtle"><strong>Captured model label</strong><br>{escape(manifest["model_label"])}</p>'
    html_start = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>BriefCheck · Research notebook</title>
<style>
:root{--paper:#fbf8f2;--white:#fffefa;--ink:#292620;--muted:#6f6a61;--line:#e5ddce;--accent:#945d16;--soft:#f4e6c9;--green:#366953;--green-bg:#e9f1e9;--shadow:0 10px 35px #3a2c1210}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px}button{font:inherit;cursor:pointer}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #c99138;outline-offset:4px}header{max-width:1250px;margin:auto;padding:30px 38px 0}.brand{display:flex;justify-content:space-between;gap:20px;align-items:center}.wordmark{font-size:17px;font-weight:800;letter-spacing:-.6px}.wordmark span{color:var(--accent)}.eyebrow{font-size:11px;font-weight:750;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}.mode{display:inline-flex;align-items:center;gap:8px;font-size:12px;background:#efe9de;border:1px solid var(--line);border-radius:999px;padding:7px 12px}.mode:before{content:"";width:6px;height:6px;background:var(--accent);border-radius:50%}.hero{padding:42px 0 27px;display:flex;justify-content:space-between;align-items:end;gap:25px}h1{font-family:Georgia,serif;font-size:clamp(31px,4vw,49px);line-height:1.12;letter-spacing:-1.4px;font-weight:500;margin:10px 0 14px}.subhead{max-width:700px;color:var(--muted);margin:0}.print-button{border:1px solid var(--line);background:var(--white);padding:10px 15px;border-radius:8px;white-space:nowrap;color:var(--ink)}.facts{display:grid;grid-template-columns:1fr 1fr 1fr 1.6fr;border:1px solid var(--line);border-radius:12px;background:var(--white);overflow:hidden}.fact{padding:16px 20px;border-right:1px solid var(--line)}.fact:last-child{border:0}.fact strong{display:block;font-size:15px;margin-top:3px}.pipeline{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:4px}.stage{font-size:13px;text-transform:capitalize;white-space:nowrap}.stage i{font-style:normal;color:var(--green);margin-right:5px}.tabs{display:flex;gap:26px;border-bottom:1px solid var(--line);margin:28px 0 0}.tab{background:none;border:0;padding:12px 0;color:var(--muted);border-bottom:3px solid transparent;font-weight:600;font-size:13px}.tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}main{max-width:1250px;padding:28px 38px 50px;margin:auto}.panel[hidden]{display:none}.brief-layout{display:grid;grid-template-columns:minmax(0,2.6fr) minmax(230px,1fr);gap:25px}.paper{background:var(--white);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:34px 38px}.brief h2{font:500 28px/1.2 Georgia,serif;letter-spacing:-.5px;margin:0 0 8px}.brief h3{font:700 11px/1.5 ui-sans-serif,system-ui,sans-serif;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);margin:30px 0 10px}.brief p{margin:8px 0}.brief li{padding-left:2px;margin:10px 0}.brief ul{padding-left:18px;margin:10px 0}.brief li::marker{color:#b78039}.citation{font-size:10px;vertical-align:super;white-space:nowrap;text-decoration:none;background:var(--soft);padding:2px 3px;border-radius:3px;margin:0 2px}.side-card{border:1px solid var(--line);padding:22px;border-radius:12px;margin-bottom:18px;background:#f5efe3}.side-card h3{font:500 23px/1.2 Georgia,serif;margin:8px 0 14px}.side-card p{color:var(--muted);font-size:13px}.side-card .big-number{font-size:36px;line-height:1.2;font-weight:600;color:var(--ink);margin:8px 0 4px}.side-card ul{margin:0;padding-left:17px;font-size:12px;color:var(--muted)}.subtle{font-size:12px;color:var(--muted);overflow-wrap:anywhere}.section-top{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:20px}.section-top h2,.review-head{font:500 29px/1.25 Georgia,serif;margin:0 0 8px}.section-top p{margin:0;color:var(--muted);max-width:760px;font-size:13px}.claim,.source{background:var(--white);border:1px solid var(--line);border-radius:9px;margin:12px 0;overflow:hidden}summary{cursor:pointer;display:flex;gap:12px;align-items:start;padding:17px 20px;font-size:13px;font-weight:500;list-style:none}summary::-webkit-details-marker{display:none}summary:after{content:"+";font-size:20px;margin-left:auto;line-height:1.3;color:var(--accent)}details[open]>summary:after{content:"−"}details[open]>summary{border-bottom:1px solid var(--line)}.pill{display:inline-flex;border-radius:4px;padding:3px 7px;background:#eee8dc;color:var(--muted);font-size:10px;white-space:nowrap;line-height:1.5}.pill.good{color:var(--green);background:var(--green-bg)}.pill.amber{color:var(--accent);background:var(--soft)}.detail-inner{padding:19px 22px}.detail-inner>p:first-child{margin-top:0}.tiny{font-size:11px;color:var(--muted)}.source-jump{font-size:11px;margin-right:14px;font-weight:600}.evidence{border-left:3px solid #ceb382;background:#f7f3ea;margin:15px 0;padding:12px 15px}.evidence blockquote{margin:7px 0 0;font:12px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.source-title{font:12px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.source-meta{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin:0}.source-meta dt{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.source-meta dd{margin:3px 0;font-size:12px;overflow-wrap:anywhere}.raw{font:12px/1.75 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f4ed;border:1px solid var(--line);border-radius:6px;padding:20px;max-height:600px;overflow:auto}.hash{font:10px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted);overflow-wrap:anywhere}.lead-small{max-width:900px;font-size:14px}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px}.comparison .paper{padding:25px;font-size:13px}.comparison .brief h2{font-size:23px}.comparison-label{margin-bottom:14px;color:var(--accent)}.diff{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:520px;overflow:auto}.diff span{display:block;padding:3px 6px}.diff-add{background:#eaf3e8;color:#254c2b}.diff-remove{background:#f9e9dc;color:#81420d}.diff-same{color:#787267}.notice{margin:22px 0;padding:18px 23px;border:1px solid #dcc7a5;border-radius:9px;background:#f7eddb}.notice h3{font-size:13px;margin:0 0 9px}.notice li{font-size:12px;margin:7px 0;color:#69573e}.notice ul{padding-left:16px;margin:0}.empty{padding:40px;border:1px dashed #ccbfa8;border-radius:10px;text-align:center}.empty h3{font:500 26px Georgia,serif}.empty p{max-width:540px;margin:auto;color:var(--muted)}footer{font-size:11px;color:var(--muted);border-top:1px solid var(--line);margin-top:40px;padding-top:16px}code{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;background:#f1ebe0;padding:2px 4px;border-radius:4px}@media(max-width:850px){header{padding:22px 20px 0}main{padding:22px 20px}.hero{display:block}.print-button{margin-top:20px}.facts{grid-template-columns:1fr 1fr}.fact:nth-child(2){border-right:0}.fact:nth-child(-n+2){border-bottom:1px solid var(--line)}.brief-layout,.comparison{grid-template-columns:1fr}.paper{padding:27px 24px}.tabs{gap:20px;overflow:auto}.tab{white-space:nowrap}.brand{align-items:start}.mode{font-size:10px;max-width:200px}.source-meta{grid-template-columns:1fr}}@media print{body{background:white;font-size:10pt}header,footer,.sidebar,.panel:not(#brief-panel),.section-top,#claim-map{display:none!important}main{padding:0;max-width:none}.brief-layout{display:block}.panel#brief-panel{display:block!important}.paper{padding:0;border:0;box-shadow:none}.brief h3{break-after:avoid}.brief li,.brief p{break-inside:avoid}.citation{font-size:7pt;background:none}.brief h2{font-size:19pt}}
</style></head><body>
"""
    content = f'''<header><div class="brand"><div class="wordmark">Brief<span>Check</span> <span class="eyebrow"> / Research notebook</span></div><div class="mode">{escape(mode)}</div></div><div class="hero"><div><div class="eyebrow">Evidence, reviewed before delivery</div><h1>{escape(final["entity_name"])}</h1><p class="subhead">A concise company brief, its original draft, and the evidence behind each editorial decision.</p></div><button class="print-button" id="print-button" type="button">Print final brief ↗</button></div><div class="facts"><div class="fact"><span class="eyebrow">Research date</span><strong>{escape(manifest["as_of"])}</strong></div><div class="fact"><span class="eyebrow">Run</span><strong>{escape(manifest["ticker"])} · {escape(manifest["version"].upper())}</strong></div><div class="fact"><span class="eyebrow">Documents</span><strong>{count} available / {len(sources)} supplied</strong></div><div class="fact"><span class="eyebrow">Completed stages</span><div class="pipeline">{stages}</div></div></div><nav class="tabs" role="tablist" aria-label="Report sections"><button class="tab" role="tab" aria-selected="true" aria-controls="brief-panel" id="brief-tab" data-tab="brief-panel">Final brief</button><button class="tab" role="tab" aria-selected="false" aria-controls="comparison-panel" id="comparison-tab" data-tab="comparison-panel">Draft & revision</button><button class="tab" role="tab" aria-selected="false" aria-controls="audit-panel" id="audit-tab" data-tab="audit-panel">Independent audit</button><button class="tab" role="tab" aria-selected="false" aria-controls="sources-panel" id="sources-tab" data-tab="sources-panel">Source browser</button></nav></header>
<main><section class="panel" id="brief-panel" role="tabpanel" aria-labelledby="brief-tab"><div class="brief-layout"><article class="paper brief">{body}</article><aside class="sidebar"><div class="side-card"><span class="eyebrow">Traceable statements</span><div class="big-number">{len(final["claims"])}</div><p>Mapped claims, each with its original source passages or an explicitly open question.</p><a href="#claim-map">Inspect the claim map ↓</a></div><div class="side-card"><span class="eyebrow">Review scope</span><h3>{"One audit.<br>One revision." if audit else "One strong<br>baseline."}</h3><p>{escape(str(finding_count) + " draft claims received an adverse audit verdict. The audit may also identify omissions." if audit else "The baseline tests what one model pass achieves before a separate critic is introduced.")}</p><p>Passing deterministic checks does not prove that a source is true or that a conclusion follows.</p></div>{model_details}<p class="subtle">{escape(manifest["model_settings"])}</p></aside></div><div id="claim-map" style="margin-top:35px"><div class="section-top"><div><h2>Follow the evidence</h2><p>Open a statement to inspect its wording, classification, period and exact supporting passages.</p></div></div>{claims}</div></section>
<section class="panel" id="comparison-panel" role="tabpanel" aria-labelledby="comparison-tab" hidden><div class="section-top"><div><h2>What changed after review?</h2><p>Both versions below are rendered from the archived model JSON. The final Markdown has no editorial rewrite after generation.</p></div></div><div class="comparison"><article class="paper brief"><div class="eyebrow comparison-label">Original draft</div>{markdown(draft["brief_markdown"])}</article><article class="paper brief"><div class="eyebrow comparison-label">Final brief</div>{body}</article></div><details class="claim"><summary>Line-by-line difference</summary><div class="detail-inner"><p class="tiny">Green lines were added; amber lines were removed. This is a mechanical text comparison, not a quality score.</p><div class="diff">{diff_rows}</div></div></details></section>
<section class="panel" id="audit-panel" role="tabpanel" aria-labelledby="audit-tab" hidden><div class="section-top"><div><h2>A second look at the first draft</h2><p>The critic starts a fresh context with the original documents and draft. These verdicts concern the original draft, not a second audit of the revised brief.</p></div></div>{review_intro}{"".join(review_rows)}<div class="notice"><h3>What this run cannot establish</h3><ul>{"".join("<li>" + escape(i) + "</li>" for i in limitations)}</ul></div></section>
<section class="panel" id="sources-panel" role="tabpanel" aria-labelledby="sources-tab" hidden><div class="section-top"><div><h2>Original documents, preserved</h2><p>All supplied text is shown literally, including frontmatter and embedded markup. Source labels and URLs are supplied metadata; BriefCheck did not verify them. Date-excluded documents never entered the model context.</p></div></div>{"".join(source_blocks)}</section>
<footer>{escape(mode)} · Prepared {escape(manifest["created_at"])} · Research cutoff {escape(manifest["as_of"])}. This report is self-contained and loads no remote resources.</footer></main>'''
    script = """<script>
(() => {
 const tabs = Array.from(document.querySelectorAll('[data-tab]'));
 function activate(id) { for (const tab of tabs) { const active = tab.dataset.tab === id; tab.setAttribute('aria-selected', String(active)); document.getElementById(tab.dataset.tab).hidden = !active; } }
 for (const tab of tabs) tab.addEventListener('click', () => activate(tab.dataset.tab));
 document.querySelector('[role="tablist"]').addEventListener('keydown', event => { const index=tabs.indexOf(document.activeElement); if(index<0)return; let next=index; if(event.key==='ArrowRight')next=(index+1)%tabs.length;else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();tabs[next].focus();activate(tabs[next].dataset.tab); });
 document.addEventListener('click', event => { const link = event.target.closest('[data-source]'); if (!link) return; const target = document.getElementById('source-' + link.dataset.source); if (!target) return; event.preventDefault(); activate('sources-panel'); target.open = true; target.scrollIntoView({behavior:'smooth',block:'start'}); });
 document.getElementById('print-button').addEventListener('click', () => window.print());
})();
</script></body></html>"""
    return html_start + content + script
