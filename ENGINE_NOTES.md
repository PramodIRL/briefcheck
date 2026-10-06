# BriefCheck: engine notes

Saved examples and the local UI work without a key. The latest Groq GPT-OSS-20B v4 run is **completed** (`v4-groq-20b-01`). Execution and zero-call replay have passed; wording and completeness still need review. Earlier free OpenRouter runs completed on older revisions but had content issues. This account then exhausted its daily free allowance. No paid OpenRouter calls were used.

Workflow: **source triage → draft → audit against original documents → revision**. BriefCheck has six successful stages; SourceLens has five. Growth and risk halves use bounded structured responses. The model writes claim sentences and selects paragraph IDs. Code inserts headings, original passages, citations and Sources without silently rewriting the model's sentences.

Both projects share passage, transport and local UI infrastructure. Their stage sequences differ; they are not independently developed engines. The original v1–v3 implementations and captured model-session experiments remain intact. The selected `v3` example predates v4 and is not represented as a v4 API result.

BriefCheck's audit is another request to the same model and has no second semantic audit after revision. Revision receives only its relevant draft half and matching audit IDs. SourceLens's writer is restricted to its accepted evidence-ledger passages. Rejected responses are retained. Repairs use the original task, the rejected assistant reply and explicit validation feedback. SourceLens provider-21 makes duplicate-removal instructions explicit after provider-20 repeated a margin sentence through two repairs; it does not weaken duplicate checks or edit reports by hand.

Source decisions are operational: excluded documents cannot be cited; context documents require retained evidence alongside them. Future-published bodies are excluded. Each run pins source bytes, original paragraphs and a code snapshot. Metadata is supplied evidence, not verified authenticity. IDs are local to the run.

Checks cover schema, passage references, numeric presence, duplicate text, some control characters, basic forecast attribution/modality and section/word limits. They do not establish semantic entailment, correct denominators, complete coverage, authentic sources or robust handling of every date/wording variant. Completed runs can still contain content errors; see CONTENT_REVIEW.json and run-notes.json.

Inputs are dated `.md`/`.txt` files with source, url, published and type frontmatter. Uploads replace the included pack. Maximums: 1 MiB per file, 4 MiB total, 32 files. A ticker alone fetches nothing. PDF is unsupported. Both UIs need only Python; the original SourceLens CLI additionally needs Node 22.18+.

Exact runtime prompts are retained with each run. `prompts/v4/` contains current shared system text; stage-specific section, ledger, repair and schema instructions are assembled by v4.py and retained in run requests. The selected brief remains an exact original copy; owner sign-off is pending.

See PROVIDER_SETUP.md for exact model settings and commands, LIVE_TEST_RESULTS.txt for all outcomes, and LEGACY_README.md for original commands. No credentials are included. No publication or assessment submission has been performed by this release process.
