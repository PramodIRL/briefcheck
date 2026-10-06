# BriefCheck · 2–3 minute recording guide

Record your own screen and explain the decisions in your own words. For the strongest demonstration, show a fresh file-handoff or API generation. Use the cached replay below to rehearse or to inspect the included experiment, and label it clearly whenever shown.

## Before recording

Open the terminal in the project folder, the final `runs/v3/report.html` in a browser, `prompts/v3/audit.md`, and `TEST_LOG.md`. Confirm the final run validates. Keep keys, other tabs and private files out of the recording.

```bash
python briefcheck.py validate --run runs/v3
```

## Suggested sequence

| Time | Show | Explain |
|---|---|---|
| 0:00–0:20 | Project and research inputs | “BriefCheck takes a ticker, documents and a research date. This assessment uses the supplied fictional company and the fixed September 23 cutoff.” |
| 0:20–0:45 | Run a command; show the mode honestly | For replay: “This checks and renders my captured run without another model call. The actual generation requests and replies are saved here.” For fresh inference: show the current request/model stage and its accepted output. |
| 0:45–1:15 | Final brief and one citation | Open a result claim and its exact source passage. Explain why the choice is appropriate for that reporting period. |
| 1:15–1:50 | Draft & revision, then Independent audit | Show one real review finding from this run, what the critic said, and how the final wording changed. If the critic found a claim sound, show that honestly rather than claiming an error was fixed. |
| 1:50–2:15 | One prompt and version log | Explain the design decision: the critic starts a fresh context with original sources, records judgments, then the agent makes one bounded revision. Use the actual v1/v2/v3 observations from TEST_LOG. |
| 2:15–2:40 | Limitations panel and source browser | “An exact quote and a valid citation do not prove a conclusion follows. The critic can share the writer's mistake, and supplied documents are not authenticated. There is no second model audit after the revision.” |

Cached replay command, if you choose that demonstration:

```bash
python briefcheck.py replay --run runs/v3 --out replays/recording-demo
```

## Fresh generation commands

With an API key and compatible model configured as described in the README:

```bash
python briefcheck.py run --ticker SRVCABLE --docs research_pack --as-of 2026-09-23 --version v3 --run runs/recording-live
```

For the model-session workflow:

```bash
python briefcheck.py prepare --ticker SRVCABLE --docs research_pack --as-of 2026-09-23 --version v3 --run runs/recording-handoff --model-label "Actual model label"
python briefcheck.py accept --run runs/recording-handoff --response path/to/fresh-draft.json
python briefcheck.py accept --run runs/recording-handoff --response path/to/fresh-audit.json
python briefcheck.py accept --run runs/recording-handoff --response path/to/fresh-revision.json
```

Generate each response from the current request in a fresh model context between the corresponding commands. This is a visible response-file handoff, not an API call. You can trim waiting time to keep the walkthrough within three minutes; disclose that editing and keep the actual generation record.

## What to make concrete

The proud design decision should be a visible source judgment or meaningful revision. Open the conflicting sources, read the recorded reasoning and point to the actual brief wording. Do not spend the recording mostly describing the UI.

The strongest limitation is one you can demonstrate: the unit test intentionally allows a wrong number through a quote-presence check to show why mechanical validation is not entailment. Describe that as a validator counterexample, not as a claim that the final output contains that error.

Before sharing, watch the clip once, confirm audio is clear, and set the recording link's access so the reviewer can open it. Creating, uploading or publishing the recording is a separate candidate action.
