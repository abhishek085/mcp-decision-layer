---
license: cc-by-4.0
language: [en]
pretty_name: spark-s1 MCP tool router - training data
size_categories: [10K<n<100K]
task_categories: [text-classification]
tags: [mcp, tool-selection, function-calling, synthetic, decision-model]
---
# spark-s1-mcp-router-train

Training data for [`spark-s1-mcp-router-4b-r1`](https://huggingface.co/abhishek085/spark-s1-mcp-router-4b-r1): yes/no records asking whether an MCP tool is needed for a task, given a short list of candidate tools.

## Files
- `data/train.jsonl` (20,700 records) and `data/validation.jsonl` (1,368 records). Record format of the Open-Spark-Jev project: `state.content` = `Task: ...` + `Candidate tools:` list (name and first 90 characters of the description); `question` = `{"type": "noul", "prompt": "Is the tool '<name>' needed ..."}`; `target` = yes/no with distribution; `meta` = task family, whether the text is the original template or a Nemotron paraphrase, whether tool aliases were used, and the gold tool list.
- `data/source_instructions_paraphrases.jsonl`: the 324 source task instructions (template wording, gold tools from code, an LLM audit of the gold list) with every Nemotron paraphrase and its checks (`slots_ok`, `qwen_verified`, `used_in_training`).
- `data/tool_aliases_raw_nemotron.json`, `data/tool_aliases_verified.json`: alternative names/descriptions for our 28 trainable tools (168 written, 75 verified).
**Not included:** the 3,000 replay rows from the original spark-s1 training mix that were also used in training (they come from other public datasets with their own licences).

**Which records trained the model.** The released model was trained on a family-balanced subset of `train.jsonl` (at most 520 records per task family, with 85% of the trivial real-catalog-tool "no" questions removed: 4,991 records, 53% positive) plus 800 replay rows (not included). The full 20,700 records are released for transparency and for your own sampling.

## How it was made
1. Tasks come from code templates over a synthetic 12-server MCP world (training salt `train`, seeds >= 100, disjoint from the evaluation worlds). Gold tool lists come from the templates, not from an LLM. Five template families and four servers' tools (hr, inventory, support, deployments) are held out of training.
2. **Paraphrases (1,422) and tool aliases (168) were written by NVIDIA Nemotron-3-Nano-30B-A3B**, then filtered by a deterministic check that every id/number/name/quoted value is preserved and **verified by Qwen3.8-27B** (same-meaning yes/no; 772 paraphrases and 75 aliases kept; the gold tool lists were also audited by Qwen: 316 of 341 judged complete, the 25 flags are one correct doc-search gold list).
3. Negative tools: real tool definitions from the `automatelab/mcp-servers-tool-catalog` dataset (6,536 tools that are not among the 2,000 used as evaluation distractors), shown with names and 90-character description snippets.
4. Candidate lists imitate inference: embedding (bge-small) top-ranked tools with the gold tools forced in; 40% of lists use verified aliases for our tools.
5. 17 source instructions identical to development/test instructions were removed before building.

## Known issues
- Narrow distribution: 11 task families on one synthetic world. A model trained on it reaches near-zero training loss quickly; about 10% of questions concern real-catalog tools (always "no") after downsampling (they were 40% in the first build).
- Verifier gap: a few accepted paraphrases drift on answer format (e.g. "reply done").
- Gold lists are template-declared; alternative valid tool paths count as misses elsewhere.
- Third-party text: tool names and short description snippets come from the automatelab catalog, which is published under CC BY 4.0; the original tool authors' own licences were not re-checked.

## Licence and attribution
This dataset is released under **CC BY 4.0**. Attribution: tool definitions derived from *mcp-servers-tool-catalog* by automatelab (https://huggingface.co/datasets/automatelab/mcp-servers-tool-catalog, CC BY 4.0). Synthetic text was generated with NVIDIA Nemotron-3-Nano-30B-A3B under the NVIDIA Nemotron Open Model License (NVIDIA does not claim ownership of outputs; licence copy in `licenses/`). Licensed by NVIDIA Corporation under the NVIDIA Nemotron Model License (courtesy notice). Code: https://github.com/abhishek085/mcp-decision-layer (Apache-2.0).
