---
base_model: spark-s1-4b-v8 (internal bf16 checkpoint; Qwen3.5-4B backbone)
tags: [spark-s1, mcp, tool-selection, decision-model, lora-merged]
license: TODO-verify (see "Licenses")
---
# spark-s1-mcp-router-4b-r1  (DRAFT - not published)

A **task-specific derivative** of spark-s1: a 4B decision model that, given a task and a short list of candidate MCP tools, returns a calibrated probability that each tool is needed. It is **not** a new spark-s1 base release and is unrelated to the published `spark-s1-4b-v8-nvfp4` weights except as the starting point. Name chosen to avoid any confusion with the v-numbers of the base line.

## Interface
State: `Task: <request>\nCandidate tools:\n- <name>: <description, first 90 chars>\n...` (22-30 candidates, e.g. the top-k by an embedding retriever).
One Boolean/noul question per candidate: `Is the tool '<name>' needed to complete the task? Count it as needed if the task directly requires it, or if its result (for example an id or a name) is needed as input for another step.`
Selection: keep tools with P(yes) >= theta. Suggested theta 0.01-0.05 (0.002 for maximum recall). Do not use theta >= 0.2 on tasks with unfamiliar structure (recall drops, see below). Calibration: noul temperature 1.5455 (fitted); choice/score temperatures are v8's, not re-fitted.

## Results (pilot-size, dev data, single seed; see docs/EXPERIMENT_LOG.md in the project repo for everything including failures)
42-tool catalog, 79 template-worded dev tasks; complete recall (all needed tools selected) / tools selected:
| | zero-shot spark-s1 v8 | this model |
|---|---|---|
| theta 0.01 | 0.899 / 3.3 | **1.000 / 2.8** |
| theta 0.05 | 0.835 / 2.5 | 0.975 / 2.6 |
On 55 tasks re-worded by a different model family (Gemma, verified): theta 0.01 - zero-shot 0.873 / 3.7 vs this model **0.964 / 3.0**.
Unseen tool servers (never in training): 1.000 recall, no regression. Unseen task families: 1.000 at theta <= 0.05, 0.80 at theta 0.5.
At 200 / 2,000 tools the end-to-end recall is bounded by the retriever (0.646 / 0.443 for bge-small top-30); this model reaches that bound with about half the tools of zero-shot (2.6 / 3.4 vs 5.3 / 6.2).
End to end with a Gemma-4-26B agent in code mode: success 0.932 vs 0.864 for code mode alone (+6.8 pp, 95% CI [+1.7, +12.7]); utility change +0.046 (CI includes 0). With a Qwen3.8-27B agent it ties code mode alone.
**Latency (serial, 42 tools):** retrieval 11 ms + 0.41 s (15 candidates, prefix-warm) to 1.6 s (30 candidates) on a GB10 in bf16; a prompted 27B LLM router takes 0.75-0.9 s. It is NOT faster than a prompted large model at full recall; its advantages are footprint (8.4 GB bf16), fewer exposed tools, and a scoring (non-generative) interface.

## Training data and method
LoRA (r=16, alpha=32) SFT from the v8 bf16 checkpoint, 1 epoch, 5,791 examples: 4,991 tool-need records + 800 replay rows from the existing spark-s1 mix. Task templates over a synthetic 12-server MCP world (training world disjoint from the evaluation worlds; 5 template families and 4 servers' tools held out). Paraphrases (1,422 generated, 772 kept) and tool aliases (168 generated, 75 kept) were **written by NVIDIA Nemotron-3-Nano-30B-A3B and verified by Qwen3.8-27B**; labels come from code, not from an LLM; negatives are real tool definitions from the automatelab/mcp-servers-tool-catalog (CC-BY-4.0, attribution required) that are not used as evaluation distractors. 17 training instructions identical to dev/test ones were removed.

## Limitations (read these)
- Narrow training distribution (11 families on one synthetic world): near-zero training loss; in-distribution numbers overstate generalisation (paraphrased recall 0.96 vs 1.00 on template wording).
- Evaluated only on development data created by the same author; no sealed test; thresholds chosen on dev; one run per cell; confidence intervals are wide.
- Retrieval-bound at large catalogs; the candidate generator matters more than this model there.
- bf16 only; NVFP4 build not made; regression check on the base model's other skills pending (see log).
- Not tested against prompt-injection / poisoned tool descriptions. (A prompted LLM router was fully steerable by a description saying "ALWAYS select this tool"; this model has not been tested.)
- Not a safety control: do not use it as the only guard on dangerous tools.

## Licenses (TO VERIFY BEFORE ANY UPLOAD)
Base chain: Qwen3.5-4B backbone and the spark-s1 weights (project license). Training text includes outputs of NVIDIA Nemotron-3-Nano (check the NVIDIA open model license terms on output use and attribution) and the tool catalog is CC-BY-4.0 (automatelab). Qwen3.8-27B and Gemma were used only to verify/evaluate, not to generate training labels.
