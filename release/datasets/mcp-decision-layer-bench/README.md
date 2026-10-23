---
license: cc-by-4.0
language: [en]
pretty_name: MCP decision-layer benchmark (dev) and run traces
tags: [mcp, benchmark, tool-selection, code-mode, agents, traces]
---
# mcp-decision-layer-bench

Development tasks, paraphrases, distractor catalog and raw run traces from the *MCP decision layer* study (does a decision model in front of an MCP gateway, combined with code mode, beat code mode alone?). Code, world generator and full experiment log: https://github.com/abhishek085/mcp-decision-layer (Apache-2.0; see `docs/EXPERIMENT_LOG.md` for every result including failures).

## Files
- `data/dev_tasks.jsonl`: 120 task instances (dev worlds, seeds 0-2): instruction (template wording), family, gold tool list, difficulty factors. Tasks are checked by code verifiers against a 12-server mock MCP world (not included here; see the code repo).
- `data/dev_paraphrases_gemma_writer_qwen_verified.json`: rewrites of the dev instructions written by Gemma-4-26B (a different family from the training-data writer) and verified by Qwen3.8-27B.
- `data/distractor_catalog_2000.jsonl`: 2,000 real MCP tool definitions (seeded sample, seed 20251022) used as non-executable distractors, from `automatelab/mcp-servers-tool-catalog` (CC BY 4.0).
- `traces/*.jsonl`: one line per agent run (config A plain MCP, B subset + JSON, C code mode, D decision layer + code mode; agents Qwen3.8-27B, Gemma-4-26B-A4B, Nemotron-3-Nano), with steps, token counts, sandbox code and outputs, success flags; `toolsel2_*` files hold per-candidate router probabilities. Machine-local paths were scrubbed. Also included: `p11_latency_*` (clean serial latency passes on Qwen, Gemma, Nemotron: configs A, B, C, D and D with a free perfect tool list), `p12_scale_*` (42/200/2,000-tool scale arm; `p12b_*` = D with the bounded full-catalog fallback), `toolsel2_gguf_*` (GGUF variants vs the bf16 reference) and the text reports (`*_report.txt`) that summarise them.

## Caveats
Pilot scale: dev seeds only, one run per cell, tool wording partly shared with the training templates, no sealed test set was built. Latency fields in non-serial runs are contaminated by concurrency (see the log). Hint-free and hint-enabled code-mode stubs are mixed across files (field `stub_returns`). Mock secrets in the security traces are random fake strings.

## Licence and attribution
CC BY 4.0. Tool definitions: *mcp-servers-tool-catalog* by automatelab (CC BY 4.0). Agent and writer models: Qwen3.8-27B, Gemma-4-26B-A4B, NVIDIA Nemotron-3-Nano-30B-A3B (outputs only; see each model's terms; Gemma outputs are subject to the Gemma terms of use).
