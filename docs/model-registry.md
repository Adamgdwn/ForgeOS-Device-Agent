# Model Registry

| Model ID | Provider | Version | Purpose | Approved For | Owner | Last Reviewed |
| --- | --- | --- | --- | --- | --- | --- |
| M-001 | Ollama | `gemma4:latest` | Local reasoning, structured JSON planning, goal-directed device rehabilitation assistance | Local A1 planning, research summaries, worker prompts, non-destructive reflection, frontier-style blocker reasoning | Adam Goodwin | 2026-05-18 |
| M-002 | Ollama | `qwen3:8b` | Fast local helper model | Low-risk triage, repetitive session checks, cheap first-pass worker prompts | Adam Goodwin | 2026-05-18 |

## Runtime Routing

ForgeOS selects models by job shape through `app.core.model_router.ModelRouter` instead of treating one Ollama model as the universal brain.

| Route | Default Selection | Purpose |
| --- | --- | --- |
| `fast_triage` | `qwen3:8b` when installed, else `gemma4:latest` | Low-risk, repetitive, cheap first-pass worker tasks |
| `general_reasoning` | `gemma4:latest` | Normal local reasoning and structured JSON planning |
| `research` | `gemma4:latest` | Device research, blocker research, firmware/source questions |
| `coding` | `gemma4:latest` via `ollama_chat/` for Aider unless overridden | Repo-aware edits and generated remediation scripts |
| `frontier` | `gemma4:latest` | Higher-risk architecture/blocker reasoning that still remains local unless escalated by policy |

Operator overrides:

- `FORGEOS_FAST_MODEL`
- `FORGEOS_REASONING_MODEL`
- `FORGEOS_RESEARCH_MODEL`
- `FORGEOS_CODING_MODEL`
- `FORGEOS_FRONTIER_MODEL`
- `FORGEOS_OLLAMA_MODEL` as the default reasoning fallback
- `FORGEOS_AIDER_MODEL` for an explicit Aider provider/model string

Worker transcripts and adapter-health snapshots record the selected route, model, source, and availability so model behavior can be audited after a run.
