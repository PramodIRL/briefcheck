# Capture notes

The recorded assessment experiments were generated through GPT-6 Astra Pro in the ChatGPT session on 6 October 2026. The requested research date was separately fixed at 23 September 2026.

The local program exported a frozen JSON request for each stage. A fresh model context received that request, generated a JSON response, and saved the response to a file. The program then imported the response through its normal acceptance and validation path. This is the supported response-file workflow, not an external model API call. Source files, requests, responses and acceptance timestamps are retained.

The exact backend model snapshot, sampling settings, generation latency, token consumption and API cost were not exposed. The manifests leave those measurements unknown. Acceptance timestamps describe local imports, not model inference time. A cached replay makes no new model calls.

The generated Markdown is saved directly from the accepted response's brief_markdown field. No final brief was manually rewritten. Unit tests use explicitly synthetic fixtures and do not count as model experiments.

## Validator correction during v3 capture

The first import of the v3 draft was rejected because the management-attribution check did not recognise “The CFO reports” in claims C9 and C10. Both claims visibly attributed the statements to the CFO and carried exact transcript quotations. The error was in the narrow keyword check.

The validator was updated to recognise CFO, CEO and their full titles, with a regression test. The **same unchanged model-draft.json** was then accepted. The original rejected bytes and error report remain under `runs/v3/rejected/`. This was two import attempts for one model generation, not a second model draft or a hand-edited response.

## Code and archive versions

The manifest's `code_sha256` records the CLI file at run preparation. The package contains the final corrected implementation, including ticker/mode checks and the v3 attribution fix, so this hash is not asserted to match every earlier preparation. Source snapshots, frozen prompt/request text, raw responses and final brief hashes are preserved. Archive verification checks those recorded artifacts with the final validator; it does not claim to restore a historical runtime or reproduce model wording through a fresh generation.
