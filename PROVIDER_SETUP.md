# Provider setup

Saved examples and the local UI work without a key. The latest Groq GPT-OSS-20B v4 run is **completed** (`v4-groq-20b-01`). Execution and zero-call replay have passed; wording and completeness still need review. Earlier free OpenRouter runs completed on older revisions but had content issues. This account then exhausted its daily free allowance. No paid OpenRouter calls were used.

Use **Groq / `openai/gpt-oss-20b`** for the documented current test configuration. The UI needs Python 3.10+, no packages, and your own Groq API key. Paste it in the password field, or create a private `.env` containing `GROQ_API_KEY=your-own-key`. Never commit that file. Saved viewing uses no key.

This model uses strict JSON schema, medium reasoning and a 4,000-token output ceiling. Requests are spaced 65 seconds apart. A stage gets at most two model repairs; transport 429/5xx retries are bounded to three attempts and waits above 70 seconds stop. The UI stops jobs after 30 minutes. Quotas belong to the account; run one app at a time. The observed 20B account limit was 8,000 tokens per minute and 1,000 requests per day. These observations are not a guarantee for another account.

Groq Qwen uses a 900-token ceiling with reasoning disabled. Older Qwen and GPT-OSS-120B tests encountered formatting, content or quota failures; these are retained. They are not the recommended deadline preset.

OpenRouter needs its own `OPENROUTER_API_KEY`. Its structured-output adapter requests compatible providers. Explicit `:free` models use a zero-price provider ceiling. Free Nemotron/DOTS attempts completed on earlier revisions but contained errors. DOTS reasoning attempts also truncated, and an Apodex request returned HTTP 400. The test account hit its 50-free-requests/day allowance. Arbitrary free models are not guaranteed compatible. This release does not recommend a paid route and no paid tests were made.

The CLI reads exported provider keys. It does not automatically source `.env`. For a fresh output folder:

```bash
export LLM_BASE_URL=https://api.groq.com/openai/v1
export LLM_MODEL=openai/gpt-oss-20b
python3 v4.py run --ticker SRVCABLE --docs research_pack --as-of 2026-09-23 --out runs/my-new-run
python3 v4.py verify --run runs/my-new-run
```

`verify` makes zero model calls. It checks stored bytes, accepted response interpretation and exact rendering; it does not certify factual correctness. Live requests send your chosen documents to the provider. Keys are not stored in runs or browser storage. Legacy settings are preserved separately in LEGACY_PROVIDER_SETUP.md.
