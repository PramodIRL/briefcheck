# BriefCheck: actual experiment log

## Setup and provenance

The original eight-document SRVCABLE pack was used for three complete experiments, with a deliberate prompt or workflow change each time. The research cutoff was **2026-09-23**. The actual model captures occurred on **2026-10-06**.

**Model:** GPT-6 Astra Pro in the ChatGPT session, with exact backend snapshot and sampling settings not exposed. Each exported stage request was given to a fresh model context. The resulting raw JSON was imported through the normal file-handoff CLI. These were actual model-session outputs, not mock responses or replays. All captures used the same model family; a fresh critic context does not make its errors statistically independent from the writer's.

No API latency, token count or cost is claimed. Import timestamps do not measure model inference time. **All final briefs are unchanged from the accepted model responses.** See `CAPTURE_NOTES.md` and each run's manifest for the method and metadata.

## Three experiments and actual observations

| Run | Design and actual model generations | What happened | What changed next |
|---|---|---|---|
| `runs/v1` | A competent direct brief and claim map. 1 generation. | Accepted: 395 words, 16 mapped claims, 6 cited sources. It correctly preferred official revenue, disclosed the conflicting article, dated the historical pledge, excluded the unrelated company and blog recommendation, and qualified the GST view. Sources omitted the supplied URLs, EBITDA/basis-point terminology lacked an explanation, and one margin/cash-conversion question lacked a supporting citation. | Add a separate audit of every draft claim and all source documents, followed by one bounded revision. |
| `runs/v2` | Draft → audit → revision, each in a fresh context. 3 generations. | All stages accepted. The audit covered 21 draft claims and all 8 documents. It judged the claims supported or appropriately qualified, asked to retain approximations such as “about two-thirds” and “about 70%,” and requested the supplied funding-mix/net-debt context. The final revision incorporated these scoped changes: 446 words, 22 mapped claims, 6 sources. Registry URLs and a plain EBITDA explanation were still absent, and an operating-event question was mixed with missing valuation information. | v3 adds full body-to-claim coverage, exact registry metadata, 3–4 Snapshot lines, attribution and consistency checks, plus clearer retail wording and separate missing-data questions. |
| `runs/v3` | Stricter draft → audit → revision. 3 generations. | The first draft import hit an attribution-validator false positive. The validator was corrected and the exact same draft accepted, as detailed below. The audit reviewed all 15 draft claims and 8 documents and requested no adverse factual correction. It suggested explicitly describing ₹620 crore as total capital expenditure and preserving observation dates. The revision made that clarification, expanded the appeal-filing question, retained the source conflict, and produced 450 words, 15 mapped claims, 20 exact supporting quotations and 6 source entries with original URLs. All final mechanical checks passed. | Use v3 as the final packaged result, while preserving the semantic ambiguity and validation limits described below. |

Total: **3 research experiments and 7 actual model generations**. The v3 false-positive rejection caused a second import of the same draft, not another model generation. There were no hidden model retries and no manually rewritten final briefs. Word counts are whitespace-separated tokens including title, headings and Sources.

## The real v3 validator failure

The original v3 draft visibly said “The CFO reports…” in C9 and C10 and supplied exact transcript quotations. The keyword-based management-attribution check recognised “management” and “company” but not “CFO,” so it rejected both claims. This was a validator false positive, not a missing attribution in the draft.

The code now recognises CFO, CEO and their full titles. A regression test covers these forms while retaining rejection of unattributed management views. The same `runs/v3/model-draft.json` was then accepted. Its bytes match both `01-draft.response.json` and `rejected/01-draft.raw.txt` exactly. The original `rejected/01-draft.validation.json` preserves the actual errors. No fresh draft was generated and no sentence was changed to force it through the checker.

## What the final review establishes

| Topic | Observation in the final brief |
|---|---|
| Financial conflict | Uses issuer revenue ₹1,248 crore and reported 18.0% growth, while disclosing the article's incompatible ₹1,428 crore / 35% figures. It does not invent a reconciliation. |
| Profitability | Uses the issuer's reported PAT growth and clearly shows the EBITDA margin falling from 12.9% to 11.2%. Rounded source figures are not treated as mathematical errors. EBITDA has a short plain-language explanation. |
| Ownership evidence | Keeps 4.1% as a proportion of promoter holdings at 30 June 2026 and the 35% article as March 2024 history. |
| Entity and injected recommendation | The audit reviews all eight documents. The separate cable-TV operator's fine and promotional blog's buy/target/consensus claims are absent from the brief. Original source text, including the hidden instruction, remains preserved as data. |
| Plans and funding | Growth guidance and planned production/capacity remain management expectations. The CFO's reported spending, funding mix and net debt/equity are attributed. |
| Collections and GST | Includes slower collections, the repricing lag and the ₹46.3 crore demand. It does not invent defaults, an appeal already filed, a final cash cost or proven immateriality. |
| Missing data | Keeps current valuation as an open question instead of using the historical article price as today's price. |
| Traceability | Every final body claim has its exact mapped text. All 20 supporting quotation objects match their original sources, and every registry entry retains its filename, publication date and supplied URL. The fictional URLs were not fetched. |

### Semantic caveats the validator cannot settle

The draft and final paraphrase management's “we think that can double in two years” as the domestic-revenue **share** potentially doubling. This is a plausible reading of the preceding 9% sentence, but the source's referent is not fully explicit. The audit marked C6 supported and did not flag that ambiguity. Quoting the original wording or explicitly labelling the interpretation would be more cautious. No precise 18% forecast is added, and the final retains management attribution. The raw draft, audit and revision are preserved so this limitation is visible.

The brief also refers to an “August call.” The transcript file explicitly supplies an August publication date, without separately dating the call in the excerpt. This is a minor inferred timing label. A stricter future prompt should distinguish “transcript published in August” from a proven call date.

The audit also suggested a process-scope statement about supplied excerpts and unverified subsequent developments. That statement is absent from the standalone brief; the revision prompt keeps process limitations in the audit/report. The README and report describe the scope, and the research-date heading should not be read as proof that external developments were verified through that date.

These are examples of correlated writer/critic judgments and why a passing quote check is not a proof of meaning. The built-in workflow performs one audit and one revision. It has no second automatic semantic audit after revision. A separate review during packaging does not become an extra hidden workflow stage or rewrite the captured final output.

## Actual program checks

Command: `python3 -m unittest discover -s tests -v`.

**34 tests passed; 0 failed.** These use synthetic fixtures for a different company and mocked HTTP transport. They are code checks, not assessment model runs or live API calls.

Tests cover source-byte preservation, stable filename-derived IDs, date gating, malformed metadata, strict JSON/schema checks, exact quotations, claim/citation agreement, body coverage, entity/date mismatches, missing audit coverage, source-registry metadata, ticker identity, mixed API/file-handoff modes, archive changes, rejected-response preservation, final-output identity, safe HTML, refusals/truncation/errors and redirect rejection. An intentional counterexample shows an incorrect number can still pass a quote-presence check when attached to a real excerpt; the model must judge whether the passage actually supports the claim.

Code review found and fixed missing ticker-title validation and API/file-handoff mode checks. The v3 capture exposed the executive-attribution false positive described above. Regression tests cover the fixes. These are real implementation observations, separate from what the model critic found.

All three completed archives passed `validate`. A v3 cached replay also passed and generated a report explicitly labelled **Cached replay · no new model call**. All three saved final Markdown files exactly equal their accepted response strings. All eight packaged source documents match the original uploaded files byte for byte.

## Provider compatibility update: 6 October 2026

After the original experiment verification above, provider configuration and transport controls were added. The current suite passes **47 tests; 0 failed**. New coverage checks configuration validation before run creation, environment settings and CLI override precedence, explicit anonymous authentication without leaking an ambient key, optional omission of the provider JSON parameter while retaining JSON/schema/evidence validation, token-parameter selection, and a three-stage mocked API run that returns different model identifiers. The run record and report distinguish the requested model selector from each provider-reported model identifier and preserve the effective API settings.

OpenRouter's public catalog and the providers' official documentation were checked. One actual anonymous OpenCode request returned HTTP 403 with `FreeTierError`. No OpenRouter or Groq key was supplied, so these code tests are not successful authenticated generations on those services. See `PROVIDER_SETUP.md` and the check records in `providers/` for the findings and limits. In particular, the longer audit and revision inputs may exceed Groq's free token allowance; full v3 success on Groq Free has not been demonstrated.

All three existing archives were validated again. Their captured prompts and model responses remain unchanged, and the final brief retains its original SHA-256 digest. This update adds no assessment experiment and does not relabel the original model captures as free-provider runs.

## Inspect the evidence

- Final exact brief: `runs/v3/brief.md`.
- Original draft: `runs/v3/01-draft.response.json`.
- Actual critic output: `runs/v3/02-audit.response.json`.
- Exact final response and claim map: `runs/v3/03-revise.response.json` and `claim_map.json`.
- Frozen stage requests: `runs/v3/01-draft.request.json`, `02-audit.request.json`, `03-revise.request.json`.
- Full source inventory and original bytes: each run's `sources.json` and `source_snapshots/`.
- Original rejected draft and reason: `runs/v3/rejected/`.

No external API benchmark, real-ticker/live-data bonus, published repository or personal screen recording is claimed. The repository link and actual recording remain the submitter's final steps.
