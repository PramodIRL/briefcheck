# BriefCheck

**Local UI added:** read [START_HERE.txt](START_HERE.txt), then run `python3 webui.py`. Saved examples work without keys. The new live Groq attempts did not complete; see [LIVE_TEST_RESULTS.txt](LIVE_TEST_RESULTS.txt). OpenRouter is still unverified with a key.

**A research brief that gets an independent edit before delivery.**

BriefCheck takes a ticker, a folder of documents and a research date. It writes a concise Markdown brief, asks a second model context to check each claim against the original sources, then makes one revision. The original draft, audit and final output stay available for review.

The supplied assessment uses the fictional company **Sarvottam Cables Ltd (NSE: SRVCABLE)** and the fixed date **2026-09-23**. Its eight original research documents are unchanged in `research_pack/`. The original assignment is preserved at `assignment/README.md`. This program does not search for the fictional company or fetch the supplied `.example` URLs.

## Free API providers

See [PROVIDER_SETUP.md](PROVIDER_SETUP.md) for current OpenRouter and Groq setup, ready-to-copy environment profiles, quota considerations and the actual OpenCode free-tier rejection. New API runs support explicit authentication/JSON modes, output budgets and timeouts, and distinguish requested selectors from provider-reported model identifiers. Existing captured assessment runs are unchanged.

## Start here

- Final generated assessment brief: `runs/v3/brief.md`.
- Open `runs/v3/report.html` in any browser for the final brief, draft/revision comparison, audit and original documents. It is one self-contained file, with no remote fonts, scripts or network requests.
- Read `TEST_LOG.md` for the actual v1/v2/v3 experiments and their limitations.
- All stage prompts live separately in `prompts/`, and response schemas in `schemas/`.

**Requirements:** Python 3.10 or later. Standard library only. No installation step, package dependencies or build command.

```bash
python --version
python -m unittest discover -s tests -v
python briefcheck.py validate --run runs/v3
python briefcheck.py replay --run runs/v3 --out replays/demo
```

`replay` checks the archived source, request and response hashes and rerenders the stored output. It makes **zero model calls**. Its report explicitly says **Cached replay · no new model call**. Choose a fresh output directory each time.

## Generate without an API key

The file-handoff workflow works with a model conversation that can return raw JSON. Every stage must start a **fresh conversation** containing only the saved system message and user message. This isolates the critic's context; it does not make the critic statistically independent of the writer when both use the same model.

```bash
python briefcheck.py prepare --ticker SRVCABLE --docs research_pack --as-of 2026-09-23 --version v3 --run runs/my-run --model-label "Name shown by your model interface; exact snapshot if known"
```

1. Open `runs/my-run/request.json`. Supply its `system` and `user` fields to the model. `request.md` contains the same request in a readable form. The full JSON response schema is included.
2. Save the model's reply as a UTF-8 JSON file, without modifying its content or adding Markdown fences.
3. Import that response:

```bash
python briefcheck.py accept --run runs/my-run --response path/to/draft-response.json
```

4. The command archives the reply and writes the next `request.json`. Use a **new model conversation** for the audit, save the raw reply, and call `accept` again. Repeat once for the revision.
5. After the revision, `brief.md`, `claim_map.json`, `validation.json` and `report.html` appear in the run folder. The final Markdown is the exact `brief_markdown` string returned by the model. It is not silently rewritten by the program.

For v1, only the first draft is required. v2 and v3 each use three separate contexts: draft, audit and revision.

If a response fails validation, its raw bytes and the error report are preserved under `rejected/`, and the current stage remains pending. Do not quietly hand-fix an output and describe it as an unchanged model generation. Preserve the failed attempt and disclose any additional model request or manual edit in the experiment log. Existing run directories are never silently overwritten.

### Model used in the captured assessment runs

The captured runs use **GPT-6 Astra Pro through the ChatGPT session**, with the exact backend snapshot and settings not exposed. The manifest records that label honestly. The model was used for both writing and review because it can follow a structured response contract and evaluate short source documents within one context. The fresh critic context allows a separate review of the draft, but using the same model can reproduce the same mistake.

These are actual captured model responses in a **manual file-handoff workflow**, not measurements of the API runner. No API latency, token usage or per-run cost is claimed for them. `accepted_at` timestamps record when local files were imported, not how long the model took to reason.

## Generate through an API

The optional API runner uses the OpenAI-compatible HTTPS Chat Completions contract. Set the endpoint and model you actually have access to. Environment values are not loaded automatically from `.env`; `.env.example` documents the names.

```bash
export LLM_MODEL="your-provider-model-id"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_API_KEY="your-key"
python briefcheck.py run --ticker SRVCABLE --docs research_pack --as-of 2026-09-23 --version v3 --run runs/api-example
```

`OPENAI_API_KEY` can be used instead of `LLM_API_KEY`. Do not commit a key. The timeout defaults to 120 seconds per request and can be set with `LLM_TIMEOUT_SECONDS` or an explicit `--timeout`. `LLM_MAX_TOKENS` or `--max-tokens` optionally sets the output budget; `LLM_TOKEN_PARAMETER` chooses `max_completion_tokens` (default) or `max_tokens`. CLI values take priority. No temperature is sent by default. Each stage sends one system message and one user message, with `response_format: {"type": "json_object"}` by default. Explicit `LLM_JSON_MODE=prompt` omits that provider parameter while retaining all local JSON/schema/evidence checks. `LLM_AUTH_MODE=none` is available only for endpoints that permit anonymous requests; it omits Authorization even if a key is present in the environment. A provider must support this contract and the selected model. JSON mode alone does not guarantee schema compliance; the local validator checks the returned object.

Refusals, truncated outputs, malformed responses, HTTP errors and timeouts stop the run with a clear error. There is no hidden retry or correction loop. Redirects are refused so the bearer credential cannot be forwarded to another endpoint. API response bodies and credentials are not printed on HTTP failure. Successful API metadata records the provider-reported model, usage, finish reason and measured call duration, when returned. The API path has mocked transport tests; actual assessment generations used file handoff.

Protocol references: [Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) and [structured outputs / JSON mode](https://developers.openai.com/api/docs/guides/structured-outputs).

## Why draft → audit → revise?

A fluent draft can hide a weak citation, a stale date or a management statement presented as fact. The critic reads the original documents and checks the actual wording of each claim. The revision then incorporates justified corrections. This gives a reviewer something concrete to inspect: the sentence, its passages, the verdict and what changed.

| Stage | Receives | Produces |
|---|---|---|
| Draft | Ticker, cutoff, raw date-eligible sources | Brief plus a map of claim text to exact source passages |
| Independent audit | The same sources and original draft | Every document's relevance decision; every claim's verdict; scoped corrections; limitations |
| Revision | Original sources, draft and audit | One revised brief and a fresh claim map |

The writer does not simply obey the critic. The revision prompt asks it to verify criticisms against the documents. There is exactly **one revision**, and no claim that it must fix every semantic issue. The final version receives deterministic checks; the automatic workflow does not run another model audit after the revision. The experiment log separately records review observations made during packaging.

### Three actual design versions

| Version | Deliberate design change |
|---|---|
| v1 | A competent single-pass cited brief with the same source-is-data boundary and fixed research date. It is the baseline, not an intentionally weak prompt. |
| v2 | Adds a grounded independent audit and one revision. Records relevance decisions for every eligible document and verdicts for every draft claim. |
| v3 | Tightens exact body-to-claim coverage, source registry metadata, 3–4 Snapshot lines, entity/date consistency and management attribution. The critic explicitly tests denominators, current versus historical evidence, and unsupported outcomes. |

No production code contains SRVCABLE-specific correct numbers, special filename exclusions for its noisy documents, or an expected stock recommendation. The optional test fixtures use a different synthetic company. The eight assessment documents are inputs, not a table of answers embedded in the agent.

## Input and evidence handling

Input documents are UTF-8 `.md` or `.txt` files under the supplied folder. A file named `README.md` is treated as instructions rather than research and excluded. Each research file should have a small scalar frontmatter block:

```text
---
source: Name of publisher
url: https://publisher.example/document
published: 2026-08-01
type: filing, transcript or news article
---
Original document text here.
```

- Raw text and original bytes are retained, including frontmatter and HTML comments. The system prompts say documents are untrusted evidence, never instructions.
- Source IDs are stable hashes of relative filenames. Adding another document does not renumber existing citations. Separate full SHA-256 hashes detect content changes.
- Documents published after the cutoff, and documents with missing or invalid publication dates, are archived but excluded from model evidence. Their metadata and exclusion reasons remain in the inventory.
- Publication date is only a coarse gate. Observation dates, old reports and forecasts still need semantic interpretation by the model.
- There is an explicit 1 MiB-per-file / 4 MiB-total input limit. An oversized input fails clearly; sources are never silently truncated.

## What is validated

The standard-library schema checker implements the schema keywords used in the checked-in schemas: types, properties, required fields, additionalProperties, enums, item schemas, minimum item/string lengths and patterns. It is not advertised as a general implementation of every JSON Schema feature.

All versions check valid JSON without duplicate keys, required response fields, valid claim IDs, the requested ticker in the title, the five required headings, the research date, a 650-word hard limit including Sources, source identity, date eligibility, exact quotations and publication-date agreement. Every non-question claim needs evidence; its inline citations must match its evidence source IDs. Claim text must occur exactly in the brief body. An audit must cover all draft claims and eligible documents exactly once. API and file-handoff responses cannot be mixed in one run, and replay checks the recorded transport mode.

v3 additionally checks:

- Full body coverage by exact claim-map text.
- Three or four nonempty Snapshot lines.
- One source-registry entry per cited ID, no duplicate or unused IDs, and original filenames, dates and supplied URLs in those entries.
- Consistent entity names for facts and management views.
- Explicit attribution/expectation words for claims labelled management views.
- No reported-fact period expressed as a future ISO date.
- No revised claim drawing on a source that the auditor classified as a different entity.

The unit tests include source/citation swaps, altered quotes, date/entity mismatches, changed source-registry metadata, missing map coverage, malicious HTML, API refusals/truncation/errors and changed archive files. One intentional counterexample shows that an **incorrect number can still pass quotation provenance checks when it cites a real quote**. The model audit must assess that meaning; the code does not pretend it has proved entailment.

## Practical limitations

1. **Provided evidence is not authenticated.** A supplied filing label or URL may be wrong. File hashes detect changes within an archive; they are not signatures proving who published it.
2. **Exact quote matching is not truth or entailment.** It proves a passage is present in the referenced text. The same-model critic can miss a misleading inference.
3. **Source selection remains a model judgment.** A filing may be the best evidence for a reported number while management's expectations remain uncertain.
4. **Prompt-injection handling is a design boundary, not a universal security claim.** The included attack can be evaluated, but a few runs on one pack cannot establish resistance to all attacks.
5. **The source folder may be incomplete or stale.** There is no live-data integration or verified current valuation feed in this submission. Missing information becomes an open question.
6. **The compact Markdown renderer supports the syntax requested by the prompts.** It escapes source/model text and supports headings, lists, bold, inline code, safe HTTP(S) links and citation navigation. It is not a full CommonMark implementation.
7. **Fresh generation is not byte-identical replay.** A new model call may choose different wording or even make different judgments. Replay only validates and displays what was previously generated.

## Submission

See `SUBMISSION_CHECKLIST.md` for the four required items and `RECORDING_GUIDE.md` for a 2–3 minute walkthrough. The candidate still needs to publish their own repository, inspect the exact final output, and make their own recording. Those external actions are not represented as already completed.
