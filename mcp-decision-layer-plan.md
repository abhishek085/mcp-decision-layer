# MCP Decision Layer: End-to-End Experiment Plan

Version 1.0 · Owner: Ab

Working title: *Decision Models Meet Code Mode: A Four-Way Ablation of MCP Gateway Designs*
Working repo name: `mcp-decision-layer`

Everything marked **Proposed** is a default for you to confirm before running. Everything marked **TBD** is decided by an earlier phase. Nothing in this plan reports a result; token and latency figures are to be measured.

---

## 0. TL;DR

**Claim to test.** A decision layer inside the MCP gateway, combined with code mode, beats code mode alone and beats a decision model alone, when measured end to end on real MCP servers with open-weight models.

**Four configurations**

| Id | Name | Who picks tools | Call shape | What reaches the agent LLM context |
|---|---|---|---|---|
| A | Plain MCP | Agent LLM, from all schemas | JSON | All schemas and every result |
| B | Decision model only | Decision model (tool subset) | JSON | Subset schemas, all results |
| C | Code mode only | Agent LLM via `search()` | Script in sandbox | 2 meta tools, one final line |
| D | Decision model + code mode | Decision model (subset, shape, fallback) | Script, JSON fallback | Subset stubs, one final line |

**Two existing projects already cover B** (jev-mcp-router, ACE-Router 2601.08276). B is a baseline to replicate. The contribution is D.

**Execution order**

1. Build the world: mock MCP servers, seeded data, programmatic tasks (Phases 0 to 3).
2. Run baselines A, B, C and a no-training D (Phases 4 to 7).
3. **Gate:** measure the oracle gap before any fine-tuning (Phase 8).
4. Only if the gate passes: generate training data, fine-tune the shape decision, run the full evaluation (Phases 9 to 12).

**Ground rules**

- Different model families fill different roles. No family both writes data and is judged on it. See Section 3.
- Labels come from code or from measured outcomes, not from an LLM's opinion, wherever possible.
- Test data is sealed until the final run.

---

## 1. Hypotheses

Notation: success = task passes its verifier; U = cost-adjusted utility (Section 7).

| Id | Hypothesis | Comparison | Falsified if |
|---|---|---|---|
| H1 | Code mode cuts tokens versus plain MCP at equal or better success on tasks with chains or large intermediate results | C vs A | C is not cheaper, or loses more than the margin in success |
| H2 | A decision model alone cuts schema tokens versus plain MCP without losing success | B vs A | Success drops by more than the non-inferiority margin |
| H3 | Adding a decision layer to code mode improves U | D vs C | D is not better than C on U with the pre-registered effect size |
| H4 | Adding code mode to a decision model improves U | D vs B | Same, versus B |
| H5 | A learned shape decision beats the best rule-based shape selector | D-learned vs D-rules | The gap between D-learned and D-rules is inside the noise |
| H6 | Code mode does not raise prompt-injection attack success compared with JSON, or the decision layer's output screening offsets any rise | A, C, D under attack | ASR(C) or ASR(D) exceeds ASR(A) beyond the margin and screening does not offset it |

**Outcome mapping.** H3 and H4 both hold: headline paper. H2 holds but H3 does not: measurement paper on B versus A and C versus A. Neither: report the oracle gap and the negative result.

**Proposed margins (confirm before running).** Non-inferiority margin for success: 2 percentage points absolute. Minimum interesting effect on U: pre-registered in Phase 0 from the pilot variance, not chosen after seeing results.

---

## 2. Assumptions and open items

**Assumptions**
- Open-weight models are already downloaded on a DGX Spark and served through OpenAI-compatible APIs.
- spark-s1 (v8 NVFP4, Qwen3.5-4B backbone) is the decision model, served at `/v1/decide` per the open-spark-jev API.
- Agent LLM #1 is Qwen 27B, supplied by you.
- This phase is API-only. Fine-tuning comes after the Phase 8 gate.

**Open items (answer in Phase 1)**

| Item | Why it matters |
|---|---|
| Exact model ids and quantizations for every role | Fills the roster in Section 3 |
| Native function calling support per model | Mode A and B validity |
| Context limit and concurrency per endpoint | Schema size at 200 tools is about 30K tokens |
| Whether the decision API exposes full option probabilities | Needed for calibration and the fallback threshold |
| Memory budget for serving several models together | Scheduling in Section 13 |
| Which MCP-Atlas servers run on the Spark | Only 89 of 500 public tasks run without API keys |

---

## 3. Model roster and role separation

### 3.1 Roles

| Role | Purpose | Family (primary) | Model id | Notes |
|---|---|---|---|---|
| SUT-1 | Agent LLM under test, primary | Qwen | `<qwen-27b-id>` | Given |
| SUT-2 | Agent LLM, generalization | Gemma | `<gemma-id>` | Different family from SUT-1 |
| SUT-3 | Agent LLM, generalization | Nemotron | `<nemotron-id>` | See flag in 3.3 |
| SUT-S | Small-model arm (SLM) | Any family, 4 to 8B | `<small-id>` | Tests the small-model hypothesis |
| Test writer | Paraphrases test task text, writes test-world free text | Nemotron | `<nemotron-id>` | Writes surface text only |
| Train writer | Same, for the training world | Gemma | `<gemma-id>` | Different family from the test writer |
| Verifier | Checks paraphrases keep every slot and meaning | Rotates | see 3.2 | Never the writer's family |
| Judge | Scores free-text answers when no deterministic check exists | Rotates | see 3.2 | Never the scored SUT's family |
| Decision model | Tool subset, shape, fallback | Qwen3.5-4B based | spark-s1 v8 | Same backbone family as SUT-1 |
| Embedding model | Retrieval baselines | Any open model | `<embedding-id>` | Baseline only |

If a fourth open family is available (Llama, Mistral, gpt-oss or similar), assign it as the test writer. That removes the flag in 3.3.

### 3.2 Separation rules

1. The train writer and the test writer are different families.
2. The verifier is not the same family as the writer whose text it checks.
3. The judge is not the same family as the SUT being scored. **Proposed rotation:** Gemma judges Qwen and Nemotron SUT runs; Nemotron judges Gemma SUT runs.
4. Data used to label training examples comes from SUT runs on the training world only. The test world is never used for labels.
5. No model sees test task text during prompt tuning. Tuning uses the dev split only.

### 3.3 Known bias flags

- **SUT-3 shares a family with the test writer.** Report SUT-3 results separately and label them. Mitigation: about 30% of test tasks use non-LLM template variants, and results are reported with and without them.
- **spark-s1 shares a backbone family with SUT-1.** Report leave-one-SUT-out results so a reviewer can see the router is not tuned to Qwen's style.
- **You wrote the decision model.** Include external decision baselines: zero-shot prompted LLM router, embedding retrieval, and hosted Jev if you can get access.

### 3.4 Roster config (fill in)

```yaml
# configs/models.yaml
sut:
  primary:   {family: qwen,     id: "<qwen-27b-id>",  endpoint: "http://<spark>:8001/v1", fn_calling: TBD, ctx: TBD}
  second:    {family: gemma,    id: "<gemma-id>",     endpoint: "http://<spark>:8002/v1", fn_calling: TBD, ctx: TBD}
  third:     {family: nemotron, id: "<nemotron-id>",  endpoint: "http://<spark>:8003/v1", fn_calling: TBD, ctx: TBD}
  small:     {family: TBD,      id: "<small-id>",     endpoint: "http://<spark>:8004/v1"}
writers:
  test:      {family: nemotron, id: "<nemotron-id>"}
  train:     {family: gemma,    id: "<gemma-id>"}
verifier:    {rule: "different family from the writer"}
judge:       {rule: "different family from the scored SUT", rotation: {qwen: gemma, nemotron: gemma, gemma: nemotron}}
decision:    {id: "spark-s1-4b-v8-nvfp4", endpoint: "http://<spark>:8400", routes: ["/v1/decide", "/v1/gate"]}
embedding:   {id: "<embedding-id>"}
sampling:    {primary_temperature: 0.0, robustness_temperature: 0.7}
```

---

## 4. Systems under test

### 4.1 Shared harness

One gateway process sits between the agent and the MCP servers. The four modes are switches on that gateway, so everything else is held constant: same servers, same task, same seeds, same turn caps.

| Setting | Value (Proposed) |
|---|---|
| JSON turn cap | 25 |
| Code turn cap | 3 (initial script plus up to 2 regenerations) |
| Per-tool timeout | 30 s |
| Sandbox | Container, no network except the gateway, CPU and memory limits, wall-clock limit |
| Stubs | Typed Python stubs generated from the tool schemas |
| Prompts | Versioned in `configs/prompts/`, tuned on the dev split only, equal tuning effort for JSON and code prompts |

### 4.2 Mode definitions

- **A.** Gateway passes all tool schemas to the SUT. SUT emits JSON tool calls. Every result returns to context.
- **B.** The decision model picks the tool subset for the request. The SUT sees only those schemas and emits JSON calls. Results return to context. Includes a `request_more_tools` escape hatch (see D-fallback) to avoid the known no-fallback gap.
- **C.** The SUT sees two meta tools. `search()` returns tool stubs, `execute()` runs a script in the sandbox. Only the final output returns to context.
- **D-rules.** Decision model picks the tool subset. A fixed rule picks the shape (Section 4.3). JSON fallback available.
- **D-learned.** As D-rules, with the shape chosen by the fine-tuned decision model. Built only if the Phase 8 gate passes.

### 4.3 Rule-based shape selector (baseline for H5)

Based on practitioner heuristics. **Proposed:** use code when expected intermediate data exceeds 10K tokens, or planned calls exceed a threshold (tuned on dev), or fan-out exceeds a threshold. Use JSON otherwise.

### 4.4 D fallback policy

The gateway falls back to JSON when any of these occurs:

1. Router confidence for the shape is below threshold τ (fit on dev, Section 10).
2. The script raises an error after the allowed regenerations.
3. The SUT calls `request_more_tools`, or a needed tool is not in the exposed subset.
4. The sandbox times out.

Fallback events are logged with their cause. Fallback rate is a reported metric.

### 4.5 Decision model interface

Typed questions over a compact state, per the open-spark-jev API. Illustrative request (match `docs/API.md` before use):

```json
{
  "state": "<task text; catalog summary; history so far; SUT descriptor>",
  "questions": {
    "shape": {"type": "choice", "instructions": "Which invocation shape fits this task?",
              "criteria": {"json": "step-by-step calls", "code": "one script over many items or large data"}},
    "tools": {"type": "noul", "instructions": "Is this tool needed for the task?"}
  }
}
```

**Catalog scale.** spark-s1 supports Choice up to 26 options and tool selection among up to 12 candidates. For 200 to 2,000 tools, compare three designs on dev: (a) embedding top-12 then spark-s1 choose, (b) server-level question then tool-level question, (c) one yes/no per tool. Keep the state under about 2,000 tokens; summarize schemas rather than passing them.

---

## 5. World building and seeding

### 5.1 Mock MCP servers

Real MCP protocol (official Python SDK), stateful, deterministic given a seed, resettable between runs, instrumented to log every call and result size.

**Proposed domains (about 12 servers, roughly 120 tools)**

| Domain | Example tools | Why |
|---|---|---|
| Issue tracker | list, get, update, comment | Fan-out and chains |
| Chat | lookup user, post message | Side effects to verify |
| Docs and knowledge base | search, read, append | Large results |
| Logs and metrics | query, aggregate, top-k | Large intermediate data |
| Calendar and email | list, create, send | Conditional branches |
| CRM and database | query, update | Joins across servers |
| Files | list, read, write | Ground truth by content |
| Billing | invoices, refunds | Numeric aggregation |
| Deployments | list, status, rollback | Exploratory diagnosis |
| HR directory | people, teams | Lookups |
| Inventory | stock, orders | Fan-out |
| Support tickets | list, triage, assign | Adaptive tasks |

### 5.2 Seeded data

**Principle:** structure and ground truth come from code. An LLM writes only free-text fields (descriptions, comments, email bodies).

1. **Entity pools** generated by script with a fixed seed: people, repos, tickets, invoices, services, timestamps.
2. **Relations** set by script (assignee, owner, parent) so cross-server joins have known answers.
3. **Free text** written by the world's writer model (Section 3.1), then checked by a script that every required field value appears.
4. **Result-size control.** Each world has knobs for rows per list and text length, so the same task can be made small, medium or large.
5. **Snapshots.** Each world seed is frozen to a snapshot file with a hash. Runs reset to the snapshot.

### 5.3 Two disjoint worlds

| | Training world | Test world |
|---|---|---|
| Free-text writer | Gemma family (train writer) | Nemotron family (test writer) |
| Servers | Servers 1 to 8 | Servers 9 to 12 plus held-out variants of 1 to 8 with different entity pools |
| Entity pools | Disjoint from test | Disjoint from training |
| Used for | Training labels, prompt-free tuning | Dev (prompt and threshold tuning) and sealed test |

Dev and test are different seeds within the test-side pool. The sealed test split is never opened until Phase 11.

### 5.4 Distractor catalogs (tool-count arm)

Arms at 20, 200 and 2,000 tools. Executable tools come from the mock servers. Distractors come from real tool descriptions in public catalogs (for example HumanMCP, which lists about 2,800 tools). Distractors are non-executable stubs that return a clear "unavailable" result. Record the distractor selection seed. Do not use synthetic padding.

### 5.5 External realism source

MCP-Atlas public subset that runs without API keys (89 of 500 tasks per one group's report; verify). Pin the harness version. Score with deterministic checks where possible, otherwise the rotated judge. Never train on MCP-Atlas public tasks; if later needed for training, split by server.

### 5.6 Injection corpus (security arm)

- Payloads in tool output, in tool descriptions, and in exception text (the three vectors seen in prior work).
- Payload goals: exfiltrate a seeded secret, call a forbidden tool, force a shape change.
- Authored by a mix of templates and LLM paraphrase from the test writer for test payloads, and the train writer for training payloads.
- All payloads run only against mock servers; no real credentials or network.

---

## 6. Task suites

### 6.1 Suites

| Suite | Source | Purpose | Size (Proposed) |
|---|---|---|---|
| S1 | MCP-Atlas runnable public subset | Realism | about 89 tasks |
| S2 | Programmatic tasks on mock servers | Control of chain length, fan-out, result size, adaptivity | pilot 100, dev 200, sealed test 300, train 3,000 (post-gate) |
| S3 | BFCL-style subset (optional) | Comparability with the Bitter Lesson paper | about 100 |

### 6.2 S2 design

**Factors**

| Factor | Levels |
|---|---|
| Chain depth | 1, 3, 6, 12, 20 |
| Fan-out N | 1, 5, 20, 50, 100 |
| Intermediate result size | about 0.3K, 5K, 25K tokens |
| Adaptivity | fixed plan, conditional branch, exploratory |
| Catalog size | 20, 200, 2,000 tools |
| Cross-server | single, two, three servers |

A full factorial is too large. Use a fractional design: 40 template families, each instantiated at several factor settings, covering every level of every factor at least several times. Each template has a code verifier that checks final server state and the final answer.

**Task creation pipeline**

1. Template (code) takes a world snapshot and parameters, produces a task spec and ground truth.
2. Writer model paraphrases the instruction (surface text only). A script checks every entity id and number is present.
3. Verifier model (different family) checks the paraphrase asks for the same thing. Failures are dropped.
4. Solvability check: a reference solver script completes the task on the snapshot. Unsolvable tasks are dropped.
5. Near-duplicate filter between splits (embedding cosine or n-gram overlap). Duplicates are dropped from train.

### 6.3 Splits and hygiene

- Split by server, by template family and by world seed. Whole template families are held out for test.
- Sealed test: stored with a hash, not opened until Phase 11.
- Dev: prompt tuning, router thresholds, fallback τ, design choices. Nothing is tuned on test.
- Contamination checks: train vs test near-duplicates, and train vs MCP-Atlas public tasks.

---

## 7. Metrics and scoring

### 7.1 Metrics

| Metric | Definition |
|---|---|
| Success | Verifier pass. Deterministic state and answer checks first; rotated judge only for free-text claims |
| Tool recall | Fraction of needed tools in the exposed subset (B, D) |
| Extra tools | Count of exposed tools not needed |
| Schema tokens | Tokens of tool definitions in the SUT context per turn |
| Result tokens | Tokens of tool results that entered the SUT context |
| Total tokens | Input plus output tokens across all SUT calls, plus the decision model's tokens |
| Latency | Wall clock end to end, plus per-component (router, SUT, sandbox, tools) |
| Router overhead | Decision model time and tokens, counted against D and B |
| Fallback rate and cause | For D |
| ASR | Attack success rate: injected goal executed |
| Utility U | success minus λt times (total tokens / 1000) minus λl times latency seconds |

### 7.2 Utility weights

Report the Pareto front (success against tokens, and success against latency) as the primary view. For a scalar U, report a grid of λ values and show where the ranking changes. **Proposed:** pre-register one primary λ pair before the pilot.

### 7.3 Judge protocol

1. Deterministic check wherever the answer is checkable.
2. Judge model from a different family than the scored SUT (Section 3.2), temperature 0, fixed rubric.
3. Human audit of 100 random judged items by you; report agreement.
4. Report which tasks used the judge.

---

## 8. Phased execution plan

Each phase lists goal, steps, outputs and a gate. Phases 0 to 8 use APIs only.

### Phase 0: Contracts and pre-registration
- **Steps:** create the repo; fix the trace schema (Section 14); write `configs/models.yaml`; write the pre-registration (hypotheses, margins, λ, stopping rules, analysis); fix the metric definitions.
- **Outputs:** repo skeleton, `PREREG.md`, config files.
- **Gate:** pre-registration committed before any result exists.

### Phase 1: Smoke tests per model role
- **Steps:** for each SUT test native function calling, JSON validity, script writing, long-context behavior at 30K schema tokens, latency and concurrency. For spark-s1 test `/v1/decide`, option probabilities, latency, batch behavior. For writers and verifiers test paraphrase quality on 20 samples.
- **Outputs:** capability table; throughput numbers; serving schedule.
- **Gate:** each SUT can call tools or write code at an acceptable rate. A SUT that cannot is dropped or moved to the small-model arm. Throughput sets the pilot size (Section 13).

### Phase 2: Build the world
- **Steps:** implement the mock servers; the seeding pipeline; snapshots and reset; instrumentation; the sandbox; the typed stub generator; the distractor loader.
- **Outputs:** 12 servers, snapshots with hashes, a smoke run of one task per server.
- **Gate:** every server resets cleanly; two runs of the reference solver on the same snapshot give identical state.

### Phase 3: Task suites and verifiers
- **Steps:** write the S2 templates and verifiers; run the paraphrase pipeline; import the S1 subset; build the pilot (100), dev (200) and sealed test (300) sets; run the QA filters.
- **Outputs:** task files with hashes, solver pass report, contamination report.
- **Gate:** 100% of kept tasks are solvable by the reference solver; no train and test near-duplicates.

### Phase 4: Baselines A and C
- **Steps:** implement both modes; tune the JSON and code prompts on dev with equal effort; run the pilot on SUT-1.
- **Outputs:** first C versus A comparison (H1 pilot).
- **Gate:** prompts frozen and committed. If C cannot match A's success on simple tasks, fix the sandbox and prompt before continuing.

### Phase 5: Mode B zero-shot
- **Steps:** compare tool selection on dev: spark-s1 designs (a), (b), (c) from Section 4.5, embedding top-k, and a prompted LLM router from a different family. Measure recall and extra tools at catalog sizes 20, 200, 2,000. Then run B end to end on the pilot.
- **Outputs:** recall table; B versus A pilot (H2 pilot).
- **Gate:** pick the best tool-subset design. If recall is too low to be usable (threshold set in Phase 0), plan a tool-subset fine-tune as well.

### Phase 6: Oracle gap analysis (go or no-go)
- **Steps:** run A and C on the pilot and dev sets for all three SUTs. For each task compute the better of A and C by U. Compare always-A, always-C, rule-based shape (Section 4.3) and the oracle.
- **Outputs:** oracle gap, and how much a rule captures, by factor (depth, fan-out, size, adaptivity, SUT).
- **Gate (pre-registered):** proceed to training only if the oracle gap exceeds the Phase 0 threshold **and** the best rule leaves a meaningful share of it uncaptured. Otherwise skip Phases 9 and 10 and write the measurement paper.

### Phase 7: Mode D-lite (no training)
- **Steps:** implement D-rules with the fallback policy; fit τ on dev; run on the pilot and dev.
- **Outputs:** D-rules versus B and C (H3 and H4 pilot); fallback cause breakdown.
- **Gate:** if D-rules already beats C and B, the fine-tune is an improvement, not a requirement. If D-rules loses to C because of missed tools, fix the subset design first.

### Phase 8: Security pilot
- **Steps:** run the injection corpus against A, C and D with spark-s1 output screening off and on; run the router-attack set (poisoned descriptions steering shape or exposing an attacker tool).
- **Outputs:** ASR table by paradigm and SUT; screening effect.
- **Gate:** none blocking. Findings feed Phase 11.

### Phase 9: Training data generation (post-gate)
See Section 9.

### Phase 10: Fine-tune the shape decision (post-gate)
See Section 10.

### Phase 11: Full evaluation
- **Steps:** unseal the test set once. Run A, B, C, D-rules, D-learned on S1 and S2 for SUT-1, SUT-2, SUT-3 and the small model, 3 world seeds each. Run the scaling arm (20, 200, 2,000 tools). Run leave-one-SUT-out for the router. Run ablations (Section 11.3). Run the full security arm.
- **Outputs:** result tables, Pareto plots, CIs, all raw traces.
- **Gate:** every run logged; no test-set tuning.

### Phase 12: Writing and release
- Write the paper from the pre-registration; release the gateway, the benchmark, the traces and the decision-model pack; write the Nokast post.

---

## 9. Training data generation (post-gate)

### 9.1 What gets generated

| Data | Generator | Label source |
|---|---|---|
| Training tasks | S2 templates over the training world; instructions paraphrased by the train writer (Gemma family) | Code verifiers |
| Shape labels | Run each training task in A-style (JSON) and C-style (code) with each SUT | Measured outcomes |
| Tool-subset labels | Gold tool lists from each task's reference solver | Code |
| Fallback labels | Cases where the chosen shape failed and the other succeeded | Measured outcomes |
| Injection screening rows | Train-side payloads in tool output | Code (known to be injected or benign) |

### 9.2 Label construction for shape

For each training task and each SUT:

1. Run JSON and code k times (**Proposed** k = 3) at the primary temperature with different world seeds.
2. Compute mean success, tokens and latency per shape.
3. Compute U per shape with the pre-registered λ.
4. **Hard label:** the shape with higher U, if the margin exceeds ε (set on dev). Otherwise the label is `defer`.
5. **Soft label:** softmax of the two U values (spark-s1 trains with soft targets).
6. Store the SUT descriptor (family, size) so the router can learn capability-dependent choices.

### 9.3 Decision-time state (no leakage)

The state contains only what is known before the call: task text, catalog metadata (server and tool counts, short descriptions), history so far, SUT descriptor, and size hints from tool metadata. It never contains outcomes, token counts or verifier results.

### 9.4 Data hygiene

- Train tasks come only from the training world and training template families.
- Near-duplicate filter against dev and test.
- Hold out a validation slice from the training world for early stopping.
- Keep per-SUT label files, so leave-one-SUT-out is a data operation, not a re-run.

---

## 10. Fine-tuning the decision model (post-gate)

### 10.1 What to fine-tune

| Decision | Fine-tune? |
|---|---|
| Shape (JSON, code, defer) | Yes. New task pack |
| Tool subset at 200 and 2,000 tools | Only if Phase 5 recall is below the pre-registered threshold |
| Fallback confidence | No. Refit the temperature on dev |
| Injection screening | No. Use as is; fine-tune only if screening recall on test-like payloads is poor |

### 10.2 Steps

1. **Add a task pack** `invocation_shape` to os-datagen: inputs from 9.3, options json, code, defer, soft labels from 9.2.
2. **Start from your bf16 checkpoints.** Only the NVFP4 build of v8 is published; its bf16 weights are reproducible from your recipe.
3. **LoRA SFT** with your existing recipe (rank 16, cross-entropy plus Brier regulariser). Mix the new pack with replay rows whose targets are v8's own predictions, so agent decisions do not regress.
4. **Calibrate** the choice temperature on the dev slice of the new pack. Your card says calibration does not transfer across domains.
5. **Quantize** with NVFP4 PTQ, with calibration prompts that include the new pack. Re-measure the quantization cost.
6. **Regression checks:** JevBench public tiers, the agent decision sets, and the injection sets from your model card.
7. **Choose τ** (fallback threshold) on dev by sweeping success against fallback rate.

### 10.3 Baselines for the learned shape router (H5)

- Rule-based selector (Section 4.3).
- Gradient-boosted classifier on hand-built features (task length, expected fan-out, result-size hint, catalog size, SUT descriptor).
- Zero-shot prompted LLM as shape router (a different family from the SUT).
- spark-s1 before fine-tuning, zero-shot.
- Oracle (upper bound).

### 10.4 Generalization checks

- Leave-one-SUT-out: train on labels from two SUTs, test on the third.
- Held-out template families and held-out servers.
- Small-model arm: does the router send the small model to JSON or code when that model is weak at code?

---

## 11. Statistical analysis plan

### 11.1 Design

- Same tasks across all configurations, so use paired comparisons.
- Primary temperature 0 with 3 world seeds. Robustness: temperature 0.7 with 3 sampling seeds on a subset.
- Unit of analysis is the task. Average over seeds within task first.

### 11.2 Tests

| Comparison type | Method |
|---|---|
| Success, paired | McNemar or paired bootstrap on task-level success |
| Tokens, latency, U | Paired bootstrap, 10,000 resamples, 95% CI |
| Non-inferiority (H2) | One-sided CI on the success difference against the margin |
| Multiple comparisons | Holm correction across the pre-registered comparisons |
| Effect sizes | Report differences with CIs, not only p-values |

### 11.3 Ablations

| Ablation | Question |
|---|---|
| D without fallback | How much does the fallback matter? |
| D with oracle tool subset | How much is lost to tool-selection errors? |
| D with oracle shape | How much is lost to shape errors? |
| Catalog size 20, 200, 2,000 | Does the benefit grow with tool count? |
| SUT family and size | Does it hold across Qwen, Gemma, Nemotron and a small model? |
| Router input without SUT descriptor | Does the router use model capability? |

### 11.4 Reporting rules

- Report every pre-registered comparison, including those that fail.
- Mark any analysis added after seeing data as exploratory.
- Report per-factor breakdowns (depth, fan-out, size, adaptivity).

---

## 12. Security arm

| Item | Plan |
|---|---|
| Vectors | Tool output, tool description, exception text |
| Configurations | A, C, D, each with and without spark-s1 output screening |
| Metrics | ASR (injected goal executed), utility under attack, false positive rate of screening on benign outputs |
| Router attack | Poisoned descriptions that try to force the shape or expose an attacker tool; measure how often the router is steered |
| Baseline context | Prior work shows tool-description attacks can reach high success on real servers. Test on your own corpus rather than assuming |
| Safety | Mock servers only, no real credentials, sandbox egress off |

**Caution.** Screening results use your own decision model's injection pack. Evaluate on payload styles not used in its training and say so.

---

## 13. Compute and scheduling

**Run count formula.** runs = configurations × SUTs × tasks × world seeds. **Example:** 5 configurations × 3 SUTs × 300 S2 test tasks × 3 seeds = 13,500 runs, plus S1 and the small-model arm. Treat this as a sizing example. Real feasibility depends on Phase 1 throughput.

**Memory.** Several models cannot always be served together at full precision. Check your unit's unified memory in Phase 1 and build a serving schedule:

| Window | Resident models |
|---|---|
| Data generation | Writer and verifier only |
| SUT runs | One SUT at a time, plus spark-s1 (about 4.9 GB) and the gateway |
| Judging | Judge only, run offline on saved traces |
| Fine-tuning | Training job only |

**Cost control.** Cache decision-model calls by state hash. Save every trace so judging and re-analysis never need re-runs. Run judging as an offline batch.

---

## 14. Repo layout, config and trace schema

### 14.1 Layout

```
mcp-decision-layer/
  gateway/            # modes A-D, router client, fallback, sandbox runner
  worlds/             # mock MCP servers, seeding scripts, snapshots (hashed)
  tasks/              # S1 importer, S2 templates, verifiers, paraphrase pipeline
  bench/              # runner, scoring, judge, stats, plots
  training/           # label builder, os-datagen pack, SFT and PTQ scripts
  security/           # injection corpus, router-attack set, screening eval
  configs/            # models.yaml, prompts/, prereg thresholds
  traces/             # raw runs (jsonl), one file per run batch
  docs/               # PREREG.md, plan, results
```

### 14.2 Trace schema (one line per run)

```json
{
  "run_id": "...", "task_id": "...", "split": "pilot|dev|test|train",
  "world_seed": 0, "snapshot_hash": "...",
  "config": "A|B|C|D-rules|D-learned", "sut": {"family": "qwen", "id": "..."},
  "router": {"id": "spark-s1-4b-v8-nvfp4", "tau": 0.0},
  "temperature": 0.0, "sample_seed": 0,
  "steps": [
    {"t": 0, "kind": "router", "decision": {"shape": "code", "tools": ["..."]}, "conf": 0.0, "ms": 0, "tokens": 0},
    {"t": 1, "kind": "llm", "tokens_in": 0, "tokens_out": 0, "ms": 0},
    {"t": 2, "kind": "tool", "name": "...", "result_tokens": 0, "ms": 0, "ok": true},
    {"t": 3, "kind": "sandbox", "ok": true, "ms": 0},
    {"t": 4, "kind": "fallback", "cause": "script_error"}
  ],
  "final": {"answer": "...", "state_hash": "..."},
  "metrics": {"success": 1, "tool_recall": 1.0, "schema_tokens": 0, "result_tokens": 0,
              "total_tokens": 0, "latency_s": 0.0, "fallbacks": 0},
  "attack": {"vector": null, "goal_executed": null},
  "versions": {"gateway": "...", "prompts": "...", "vllm": "...", "model_hashes": {"sut": "...", "router": "..."}}
}
```

---

## 15. Task order and scope

Work proceeds in this order. Do not start a step until the output of the previous one exists.

| Step | Work | Output needed before moving on |
|---|---|---|
| 1 | Phases 0 and 1: contracts, pre-registration, smoke tests | Capability table, frozen config |
| 2 | Phases 2 and 3: world, seeding, task suites | Solver-verified tasks with hashes |
| 3 | Phases 4 and 5: baselines A and C, mode B zero-shot | Frozen prompts, tool recall table |
| 4 | Phase 6: oracle gap | **Go or no-go decision** |
| 5 | Phases 7 and 8: D-lite, security pilot | D-rules versus B and C, ASR table |
| 6 | Phases 9 and 10 (only if step 4 passed): training data, fine-tune | Calibrated, quantized shape router |
| 7 | Phase 11: full evaluation | Complete traces and result tables |
| 8 | Phase 12: writing and release | Paper draft, released artifacts |

**Cut list, in order, if scope must shrink**

1. Drop S3 (BFCL-style subset).
2. Drop the 2,000-tool arm; keep 20 and 200.
3. Drop the third SUT.
4. Drop the router-attack set.
5. Fall back to a measurement paper on A, B, C and D-rules (no fine-tune).

---

## 16. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Oracle gap is small | Gate in Phase 6; measurement paper is still publishable |
| spark-s1 misses needed tools | Measure recall early (Phase 5); fallback with `request_more_tools`; compare with embedding and prompted routers |
| D loses to C because the subset drops tools | Oracle-subset ablation; fix the subset design before the learned shape |
| Labels depend on the SUT | Per-SUT label files; leave-one-SUT-out; SUT descriptor as input |
| Same-family bias | Role separation (Section 3); flag SUT-3; template-only test variants |
| You authored the router | External decision baselines; locked test; pre-registration |
| Judge noise | Deterministic checks first; rotated judge; human audit of 100 items |
| Code mode brittle in one model | Equal prompt tuning on dev; report per-SUT |
| Prompt or sandbox tuning favors one mode | Equal effort budget; freeze prompts before the pilot |
| Benchmark saturation or unrealistic tasks | Combine S1 realism with S2 control |
| Quantization shifts probabilities | Re-calibrate on the quantized model; re-measure regressions |
| Scope grows | Cut list in Section 15 |

---

## 17. Release checklist

- [ ] `PREREG.md` committed before the pilot
- [ ] Prompts, configs and model hashes committed
- [ ] World snapshots with hashes
- [ ] Sealed test opened exactly once, with log
- [ ] All traces released (jsonl)
- [ ] Gateway, benchmark and training pack released
- [ ] Decision-model pack and weights (if fine-tuned)
- [ ] Failure cases and negative results reported
- [ ] Contamination and judge-audit reports
- [ ] Reproduction script: one command per phase

---

## Appendix A: Pre-registration template

```
Hypotheses: H1..H6 (Section 1)
Primary metrics: success, total tokens, latency, U (primary lambda: ___)
Margins: non-inferiority ___ pp; minimum effect on U ___
Gate (Phase 6): proceed if oracle gap > ___ and rule captures < ___% of it
Tool recall threshold (Phase 5): ___
Sample sizes: pilot ___, dev ___, test ___, seeds ___
Analysis: paired bootstrap, Holm correction, ablations listed in 11.3
Exclusions: tasks failing the solver check; runs with infrastructure errors (logged)
Stopping rule: ___
Deviations: logged and labeled exploratory
```

## Appendix B: Example S2 template

```
Template: "per-item reminder"
  Parameters: N items (fan-out), result size level, servers = issue tracker + chat
  Ground truth (code): list of N (assignee, issue) pairs from the snapshot; expected messages sent
  Verifier: chat server state contains exactly N messages with the correct recipients and ids
  Instruction (before paraphrase): "For each of the {N} open bug issues in {repo}, message the assignee a reminder naming the issue."
  Paraphrase check: all {N}, {repo} and issue-id slots present; same action requested
  Variants: N in {5, 20, 50, 100}; with and without a branch ("skip issues already closed today")
```

## Appendix C: Questions to settle in Phase 1

1. Exact model ids, quantizations and serving stack per role.
2. Native function calling support per SUT.
3. Context and concurrency limits per endpoint.
4. Whether the decision API returns full option probabilities.
5. Which MCP-Atlas servers run on the Spark.
6. Whether a fourth model family is available for the test writer.