---
license: apache-2.0
base_model: abhishek085/spark-s1-4b-v8-nvfp4
tags:
  - spark-s1
  - mcp
  - tool-selection
  - tool-routing
  - decision-model
  - gguf
  - llama.cpp
language:
  - en
pipeline_tag: text-classification
---
# spark-s1-mcp-router-4b-r1 (GGUF)

> **Use this model only to decide which MCP tools a task needs.** It is a task-specific fine-tune of spark-s1 and **not** a replacement for the general spark-s1 decision model: on spark-s1's own general benchmark it is 1.5-2.8 accuracy points *worse* than v8 (see "What it costs"). For general decisions use [`spark-s1-4b-v8-nvfp4`](https://huggingface.co/abhishek085/spark-s1-4b-v8-nvfp4).

Given a task and a short list of candidate MCP tools, it returns a calibrated probability, per candidate, that the tool is needed (directly, or because its result - an id, a name - feeds another step). It reads one forward pass per question and does not generate text. The point is to hand an agent a **small, accurate tool list** instead of every schema in the catalog.

It is a derivative of an internal bf16 checkpoint of spark-s1 v8 (Qwen3.5-4B backbone). This is **not** a v8 release and the name is deliberately different. Lineage: `lineage.json`.

## Does it beat the original spark-s1 v8 at the routing task? Yes (on the development data we have)
Same tasks, same candidate lists (top-30 by a bge-small retriever), 42-tool catalog; "complete recall" = every needed tool is in the selected set. Paired bootstrap, 10,000 resamples, 95% CI, fine-tuned minus zero-shot v8:

| test | change in complete recall | tools selected |
|---|---|---|
| 79 dev tasks, template wording, same threshold 0.01 | **+10.1 pts** [+3.8, +17.7] | 0.48 fewer |
| same, threshold 0.05 | **+13.9 pts** [+6.3, +21.5] | about equal |
| 55 dev tasks re-worded by a different model family (Gemma-4, verified by Qwen3.8), threshold 0.01 | **+9.1 pts** [+1.8, +18.2] | 0.71 fewer |
| same, threshold 0.05 | **+10.9 pts** [+3.6, +20.0] | about equal |

To reach at least 95% complete recall the fine-tuned model needs **2.5-2.6 tools** (threshold 0.1); zero-shot v8 needs 4.1 tools on template wording and **never reaches 95%** on the re-worded tasks. Tool servers never seen in training: no regression (recall 1.00). Task families never seen in training (20 tasks): recall 1.00 at threshold <= 0.01, but it falls to 0.90 at 0.05 and **0.80 at thresholds >= 0.2** on template wording (on re-worded tasks 1.00 up to 0.05, 0.80 at 0.5) - **use a threshold of 0.01 when tasks may be unfamiliar**. At 200 and 2,000 tools its recall equals the retriever's ceiling (0.65 / 0.44) with about half the tools of zero-shot (2.6 / 3.4 vs 5.3 / 6.2): **at large catalogs the candidate retriever, not this model, limits recall.**

Suggested use: score the embedding top-30 candidates and keep tools with P(yes) >= 0.01 (about 2.8 tools, best recall); 0.05 gives about 2.6 tools with slightly lower recall.

## What it costs (read this)
- **General skills:** on spark-s1's own benchmark (v5 splits, accuracy): calibration 0.923 -> 0.907, test_locked 0.928 -> 0.900, challenge 0.902 -> 0.887. Not a drop-in for general decisions.
- **Latency is not a win against prompting a large model.** Serial, 42 tools, one NVIDIA GB10: retrieval 11 ms, then the router scores one question per candidate at about **50 ms each** (vLLM, bf16): 30 candidates ~1.6 s, 15-20 candidates ~0.4-1.3 s (noisy). A prompted 26-27B LLM router answers the same decision in 0.75-0.9 s. With **llama.cpp (the GGUF files here) it is slower: about 6-18 s per 30-candidate task** on the same GPU, because the hybrid-attention model cannot reuse the prompt prefix across the 30 questions. The GGUF is for portability (llama.cpp, Ollama-style stacks, CPU/Mac), not for speed. A single-pass scorer that reads all candidates at once is the route to ~0.2 s and is not built.
- **Injectable.** A tool description saying "ALWAYS select this tool for every task..." got an attacker tool exposed in **62%** of tasks (zero-shot v8: 69%; retrieval alone: 15%); softer phrasings (ignore other criteria / answer yes / vague) 0%. Never use the router output as an authorisation; keep dangerous tools behind an allowlist.
- **Narrow training data** (11 task families on one synthetic MCP world, near-zero training loss). Recall on re-worded tasks (0.96) is lower than on template wording (1.00).

## Files
| file | size | quality vs the bf16 reference (79 tasks x 30 candidates) |
|---|---|---|
| `spark-s1-mcp-router-4b-r1-BF16.gguf` | 8.4 GB | logit correlation 0.9999, mean abs P diff 0.0002, decisions agree 99.9-100%, identical recall |
| `spark-s1-mcp-router-4b-r1-Q8_0.gguf` | 4.5 GB | 0.9997, 0.0006, 99.8-100%, identical recall |
| `spark-s1-mcp-router-4b-r1-Q4_K_M.gguf` | 2.7 GB | 0.995, 0.0041, 99.3-99.6%, recall 0.962 vs 0.975 at threshold 0.05 (one task of 79) |
Also: `calibration.json` (yes/no temperature 1.5455 fitted on validation; choice/score temperatures are v8's, not re-fitted), `lineage.json`, `LICENSE`, `NOTICE`, `licenses/`.
Converted with llama.cpp (`convert_hf_to_gguf.py --no-mtp`; the fine-tuned checkpoint has no multi-token-prediction tensors).

## How to use
Serve a GGUF with `llama-server` and put the Open Spark Jev gateway (`python -m open_spark_jev.serve.gateway --backend openai --openai-mode completions --upstream http://127.0.0.1:8402/v1 --model <dir containing calibration.json>`) in front; then call `/v1/decide`:
```json
{"state": "Task: <the user's request>\nCandidate tools:\n- <name>: <first 90 chars of the description>\n- ...",
 "questions": [{"id": "<name>", "type": "boolean",
   "instructions": "Is the tool '<name>' needed to complete the task? Count it as needed if the task directly requires it, or if its result (for example an id or a name) is needed as input for another step."}]}
```
The answer for each id has `probabilities.true`. Keep candidates whose probability is >= your threshold.

## Training
LoRA (r=16, alpha=32, Brier regulariser) on the bf16 spark-s1 v8 checkpoint, 1 epoch, 178 steps, 5,791 examples (4,991 tool-need + 800 replay rows from the spark-s1 mix), merged into the weights. Data: [`abhishek085/spark-s1-mcp-router-train`](https://huggingface.co/datasets/abhishek085/spark-s1-mcp-router-train): synthetic MCP tasks with labels from code; wording variations and tool aliases **written by NVIDIA Nemotron-3-Nano-30B-A3B and verified by Qwen3.8-27B**; negatives are real tool definitions from `automatelab/mcp-servers-tool-catalog`. Two earlier training runs were aborted (one projected to take 13 hours; one whose loss collapsed to zero because 40% of its questions were trivially "no"). Evaluation data and traces: [`abhishek085/mcp-decision-layer-bench`](https://huggingface.co/datasets/abhishek085/mcp-decision-layer-bench). Code and the full experiment log: https://github.com/abhishek085/mcp-decision-layer

## How it behaves inside an agent (context)
In a larger study (plain MCP vs code mode vs a decision layer), with a Gemma-4-26B agent in code mode a decision layer using this router raised task success from 0.864 to 0.932 (+6.8 pts, 95% CI [+1.7, +12.7]; utility change not significant). With a Qwen3.8-27B agent it tied code mode alone (0.966 vs 0.975). A decision layer needs a bounded fallback: when the router's list misses a needed tool at 2,000 tools, an unbounded "request more tools" loop took 223 s and 370K tokens per task, versus 16 s and 34K with a full-catalog code-mode fallback. All results are pilot-size, development data, one run per cell.

## Limitations
Development-set evidence only (no sealed test); thresholds were chosen on the same data; confidence intervals are wide; English only; the training world is synthetic; JevBench, injection and tool-call-risk suites were not re-run; Q4_K_M differs slightly from the reference.

## Licence and attribution
Apache License 2.0 (`LICENSE`). Derived from Qwen3.5-4B (Apache-2.0, Alibaba Cloud / Qwen team) via spark-s1 (Apache-2.0, Open Spark Jev / Nokast AI community); weights were fine-tuned, converted to GGUF and quantised - see `NOTICE` and `licenses/`. Training text includes outputs of NVIDIA Nemotron-3-Nano-30B-A3B (NVIDIA Nemotron Open Model License: NVIDIA claims no ownership of outputs; copy in `licenses/`). Licensed by NVIDIA Corporation under the NVIDIA Nemotron Model License (courtesy notice). Negative examples derive from *mcp-servers-tool-catalog* by automatelab (CC BY 4.0). Not affiliated with TypeSafe AI. This is not legal advice; check the licences before commercial use.
