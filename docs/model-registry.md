# Model Registry

| Model ID | Provider | Version | Purpose | Approved For | Owner | Last Reviewed |
| --- | --- | --- | --- | --- | --- | --- |
| M-001 | Ollama | `gemma4:latest` | Local general reasoning, structured JSON planning, goal-directed device rehabilitation assistance | Local A1 planning, worker prompts, non-destructive reflection, general fallback reasoning | Adam Goodwin | 2026-05-24 |
| M-002 | Ollama | `qwen3:8b` | Fast local helper model | Low-risk triage, repetitive session checks, cheap first-pass worker prompts | Adam Goodwin | 2026-05-18 |
| M-003 | Ollama | `deepseek-r1:14b` | Local reasoning escalation model | Device research, blocker research, firmware/source questions, higher-risk architecture/blocker reasoning before policy escalation | Adam Goodwin | 2026-05-24 |
| M-004 | Ollama | `qwen3-vl:8b` | Local vision-language model | Screenshot analysis, OCR, UI/preview inspection, visual evidence review | Adam Goodwin | 2026-05-24 |
| M-005 | Ollama | `gpt-oss:20b` | Heavy local reasoning and agentic tool-use model | Quality-first frontier route when the task justifies slower local inference | Adam Goodwin | 2026-05-24 |

## Runtime Routing

ForgeOS selects models by job shape through `app.core.model_router.ModelRouter` instead of treating one Ollama model as the universal brain.

| Route | Default Selection | Purpose |
| --- | --- | --- |
| `fast_triage` | `qwen3:8b` when installed, else `gemma4:latest` | Low-risk, repetitive, cheap first-pass worker tasks |
| `general_reasoning` | `gemma4:latest` | Normal local reasoning and structured JSON planning |
| `research` | `deepseek-r1:14b`, then `gpt-oss:20b`, then `gemma4:latest` | Device research, blocker research, firmware/source questions |
| `coding` | `qwen2.5-coder:14b` when installed, then optional `qwen3-coder:30b`, then `gemma4:latest` via `ollama_chat/` for Aider unless overridden | Repo-aware edits and generated remediation scripts |
| `frontier` | `gpt-oss:20b`, then `deepseek-r1:14b`, then `gemma4:latest` | Higher-risk architecture/blocker reasoning that still remains local unless escalated by policy |
| `visual_inspection` | `qwen3-vl:8b` when installed, else `gemma4:latest` | Screenshot, OCR, UI, preview, and visual evidence tasks |

Operator overrides:

- `FORGEOS_FAST_MODEL`
- `FORGEOS_REASONING_MODEL`
- `FORGEOS_RESEARCH_MODEL`
- `FORGEOS_CODING_MODEL`
- `FORGEOS_FRONTIER_MODEL`
- `FORGEOS_VISION_MODEL`
- `FORGEOS_OLLAMA_MODEL` as the default reasoning fallback
- `FORGEOS_AIDER_MODEL` for an explicit Aider provider/model string

Worker transcripts and adapter-health snapshots record the selected route, model, source, and availability so model behavior can be audited after a run.
