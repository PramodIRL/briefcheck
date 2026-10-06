# Free API provider setup

**Later live-test update, 6 October:** the original compatibility guidance below is not a success claim. Groq was now tested with a real key and no full workflow completed. The Groq example now uses Qwen 3.8 with explicit reasoning/output settings for diagnosis, not as a proven replacement. See `LIVE_TEST_RESULTS.txt`. OpenRouter remains unverified with a key. `LLM_REASONING_EFFORT` optionally sends none/minimal/low/medium/high; omit it to retain provider defaults, and use only values supported by the chosen model.

Checked **6 October 2026**. Provider availability and quotas can change. These instructions configure new API runs; the three included assessment experiments remain the original ChatGPT file-handoff captures.

## Which provider to choose

| Provider | Suggested model | Current finding |
|---|---|---|
| OpenRouter | `google/gemma-4-31b-it:free` | First setup to try for this project. The live catalog lists zero input/output prices, a 262,144-token context and `response_format` support. The Free plan lists 50 requests/day. A successful authenticated generation on your account is still needed. |
| Groq | `openai/gpt-oss-120b` | Chat Completions and JSON mode are documented. Its published Free limits are 30 requests/minute, 1,000/day, 8,000 tokens/minute and 200,000/day. The token limits may prevent the longer stages from fitting. |
| OpenCode | Hosted Console/Zen inference | The endpoint family is compatible, but the actual free-model test returned HTTP 403 `FreeTierError`. Do not rely on it as a direct free API for this script. |

This is a compatibility-based starting choice, not a quality benchmark of the free models. The existing evidence checks remain important when trying a smaller or different model.

## OpenRouter: recommended first setup

Create your own key at [OpenRouter API keys](https://openrouter.ai/settings/keys). Copy `providers/openrouter.env.example` to `.env`, then put the real key in `LLM_API_KEY` locally.

```dotenv
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=your-real-openrouter-key
LLM_MODEL=google/gemma-4-31b-it:free
LLM_AUTH_MODE=bearer
LLM_JSON_MODE=json_object
LLM_TOKEN_PARAMETER=max_tokens
LLM_MAX_TOKENS=16384
LLM_TIMEOUT_SECONDS=300
```

The catalog advertises `max_tokens` for this model, so the preset selects that parameter. The output budget is a starting ceiling, not a claim that the model will consume that many tokens. The structured evidence/audit can be much longer than the final one-page prose. If a response is truncated, increase the budget within the model's supported ceiling or use a more concise prompt in a new experiment.

A second currently listed option is `nvidia/nemotron-3-super-120b-a12b:free`; its catalog entry also lists `response_format`. Evaluate it with the same source pack before relying on its answers.

`openrouter/free` is available if you want the service to choose a free model. It can select a different model for each call. Prefer a named model for comparing prompt versions, and inspect the recorded provider-reported identifier either way. The app does not automatically fall back to paid model IDs.

The public Gemma model page and live catalog agree on its free status at this check. An older `openai/gpt-oss-120b:free` page still loaded, but that ID was absent from the fetched live catalog, so it is not the supplied preset. Do not infer current availability solely from an old model-page URL or assume adding `:free` works for every model.

Sources: [Gemma model page](https://openrouter.ai/google/gemma-4-31b-it:free), [live model catalog](https://openrouter.ai/api/v1/models), [Free plan pricing](https://openrouter.ai/pricing), [free router](https://openrouter.ai/docs/guides/routing/routers/free-router). A small catalog snapshot is saved at `providers/openrouter-catalog-check.json`. It is a public metadata lookup, not an inference success record.

## Groq: compatible, with smaller token allowances

Create a Groq key at [Groq API keys](https://console.groq.com/keys), stay on the Free plan, and use `providers/groq.env.example`:

```dotenv
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=your-real-groq-key
LLM_MODEL=openai/gpt-oss-120b
LLM_AUTH_MODE=bearer
LLM_JSON_MODE=json_object
LLM_TOKEN_PARAMETER=max_completion_tokens
LLM_MAX_TOKENS=
LLM_TIMEOUT_SECONDS=300
```

`openai/gpt-oss-20b` is another documented option with the same published free quotas. A payment method is documented as necessary for upgrading to the paid Developer plan. These instructions do not require that upgrade. Check your own organization's [Limits page](https://console.groq.com/settings/limits), since the published table allows exceptions.

The recorded v3 inputs contain these measured UTF-8 text sizes, excluding transport wrappers:

| Project/stage | System + user bytes |
|---|---:|
| SourceLens evidence | 13,133 |
| SourceLens writer | 25,598 |
| BriefCheck draft | 19,322 |
| BriefCheck audit | 34,392 |
| BriefCheck revision | 57,896 |

These are **bytes, not token counts**, and new model outputs change later request sizes. For rough planning, the largest request is around 14,500 tokens under a four-bytes-per-token heuristic, so the 8,000-token/minute free quota is a real concern. That estimate is not a provider tokenizer measurement. A large model context window does not override account quotas. Waiting helps cumulative rate limits but does not shrink an individually oversized request; lowering the completion budget does not shrink the input.

Start with a v1 compatibility run if using Groq. A full v3 run may require smaller intermediate records or a different provider. No prompt-compaction or automatic pacing/retry was added in this update, and full v3 success on Groq Free has not been demonstrated.

Sources: [OpenAI compatibility](https://console.groq.com/docs/openai), [current quotas](https://console.groq.com/docs/rate-limits), [JSON output support](https://console.groq.com/docs/structured-outputs), [billing](https://console.groq.com/docs/billing-faqs).

## OpenCode: actual free-tier rejection

The [current inference documentation](https://opencode.ai/v2/docs/console/inference/) publishes this API base:

```text
https://opencode.ai/inference/openai/v1
```

It says free chat models can omit Authorization. However, a real anonymous request to that documented Chat Completions endpoint with `big-pickle` and a tiny JSON task returned HTTP 403:

```text
OpenCode's free tier can only be used from within OpenCode
```

The exact request and result are preserved at `providers/opencode-api-check.json`. No successful inference occurred, so the test does not establish JSON-mode support. A [firsthand report in the official repository](https://github.com/anomalyco/opencode/issues/49621) describes the same eligibility error for third-party clients even with a valid key. Creating a key should not be presented as a fix for this restriction.

Use OpenCode's own client for its permitted free offering if that suits your workflow; the existing prepare/accept workflow can capture a model-session response. A direct API run in these scripts should use a provider/account that permits it. The generic API settings below do not bypass provider access rules. Paid Console/Zen and the paid Go coding subscription are separate offerings, and no paid OpenCode setup is included or required here.

## Run the project

From the extracted BriefCheck folder, after creating `.env` from the selected template, load its variables in a Bash-compatible shell:

```bash
set -a
. ./.env
set +a
python3 briefcheck.py run --ticker SRVCABLE --docs research_pack --as-of 2026-09-23 --version v3 --run runs/openrouter-v3
```

The Python CLI does not auto-load `.env`. For an initial Groq check, use `--version v1 --run runs/groq-v1`. Existing `--timeout` and `--max-tokens` flags override the corresponding environment values when explicitly supplied.

Use a **new output directory** for every generation. API runs record the requested model selector, the identifier actually returned by the provider, effective endpoint/settings and available usage metadata. Provider identifiers are not proof of a pinned backend snapshot. A fresh run creates its own brief; it need not match the included ChatGPT brief byte for byte.

## Optional compatibility controls

| Environment setting | Meaning |
|---|---|
| `LLM_AUTH_MODE=bearer` | Default. Send a real key in Authorization. `LLM_API_KEY` takes priority over `OPENAI_API_KEY`; blank values no longer shadow the fallback. |
| `LLM_AUTH_MODE=none` | Explicitly omit Authorization, including any ambient key. Use only with endpoints that permit anonymous access. This does not remove a provider's eligibility restriction. |
| `LLM_JSON_MODE=json_object` | Default. Ask the provider for JSON mode. Local schema and evidence checks still apply. |
| `LLM_JSON_MODE=prompt` | Explicitly omit `response_format` for an otherwise compatible model that rejects that parameter. JSON instructions and all local validators remain active. There is no automatic fallback to this mode. |
| `LLM_TOKEN_PARAMETER` | Choose `max_tokens` or `max_completion_tokens` according to the provider/model. Only the selected field is sent. |
| `LLM_MAX_TOKENS` | Optional positive integer output budget. Blank leaves the provider default. |
| `LLM_TIMEOUT_SECONDS` | Request timeout, default 120, range 1–600 seconds. |

Only change one provider profile at a time. Provider-specific names such as `GROQ_API_KEY` are not automatically read; put the corresponding key in `LLM_API_KEY`. Keep credentials local and out of the repository and recording.

## Errors and what to check

| Result | Next step |
|---|---|
| HTTP 401 | Check that the key belongs to the selected provider and that bearer authentication is enabled. |
| HTTP 403 | Check model/account eligibility. The OpenCode failure above is an eligibility rejection. |
| HTTP 400 or 404 | Check the exact live model ID, API base and supported request parameters. A base stops before `/chat/completions`. |
| HTTP 429 | Check minute/day quotas and provider capacity. Respect the provider's retry guidance. Do not repeatedly resend an oversized request. |
| `finish_reason=length` | The structured response was truncated. Increase the supported output budget or reduce requested output in a new prompt version. |
| Local validation rejection | Inspect the preserved raw response and actual error. Keep the strict checks; a new provider can still produce bad claims or formatting. |

There is no automatic retry or API resume command. A failed API run preserves its pending directory; use a new directory after correcting the issue. Do not mix manually captured responses into an API run.

## What was actually verified

The provider docs and public OpenRouter model catalog were checked. One real anonymous OpenCode request was made and rejected with 403. No OpenRouter or Groq API key was supplied, so no successful authenticated generation on either service is claimed. The new transport controls are exercised by deterministic local tests with synthetic responses. The original three model experiments and exact final briefs remain intact.
