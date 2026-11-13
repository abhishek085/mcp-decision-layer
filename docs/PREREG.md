# PREREG (written 2026-10-22, AFTER the A-vs-C pilot v1/v2 on Qwen)
Everything below applies to results produced AFTER this commit. Pilot v1/v2 A-vs-C results are exploratory.

Hypotheses: H1 code mode (C) vs plain MCP (A); H2 router+JSON (B) vs A; H3 router+code (D) vs C; H4 D vs B; H5 a learned shape router vs rules; H6 code mode does not raise attack success.
Primary metrics: success, total tokens, latency, U = success − λt·(tokens/1000) − λl·latency_s. Primary λ pair: λt = 0.01, λl = 0.002 (chosen before seeing D/B results; a grid is also reported).
Margins: success non-inferiority 2 pp (note pilot n=36 pairs cannot resolve this; confirmatory runs need ≥ ~300 task-seed pairs per arm). Minimum effect on U: 0.03 (≈ 3 pp success or 3K tokens at primary λ).
Gate: proceed to training only if oracle(U over {A,C}) − max(always-A, always-C) > 0.03 AND the best rule captures < 60% of that gap.
Tool recall threshold: ≥ 0.95 at catalog size 20 and ≥ 0.90 at 200.
Sample sizes: pilot = 18 tasks × 3 seeds; dev and sealed test sets are NOT yet built (tasks use World(salt="dev")); sealed test will use salt="test" and be opened once.
Analysis: paired bootstrap (5,000+ resamples), Holm correction over H1–H6.
Exclusions: runs with infrastructure errors (logged, counted separately). Tasks failing the solver check.
Thinking mode: pilots use Qwen thinking OFF (enable_thinking=false); a thinking-ON subset is a pre-declared robustness arm.
Latency: only from serial passes (concurrency 1, no other SUT active).
Deviations: logged and labelled exploratory.

---
## Confirmatory protocol (written 2026-10-29, BEFORE any run on the test split)
Everything above this line was exploratory (dev worlds, harness changed during the study). Everything below is fixed before the sealed test is run.

**Test split.** World salt `test`, seeds 0, 1, 2, size `medium`: 119 task instances (41 / 38 / 40 after the QA filter; every kept task is solvable by its reference solver and deterministic, verified). These worlds were not used for tuning or for training; the router's training data only excluded instructions identical to test-suite instructions (no outcomes were read).

**Frozen configuration** (git tag `confirmatory-freeze-v1`): harness and prompts as committed; code-mode stubs carry hand-written return shapes; thinking disabled; temperature 0; router = spark-s1-mcp-router-4b-r1 (bf16, vLLM), top-30 embedding candidates, threshold 0.05; D fallback policy `full_code`; `request_more_tools` capped at 2 calls; sandbox 3 executions; 900 s per-run cap.

**Agents:** Qwen3.8-27B, Gemma-4-26B-A4B (NVFP4), Nemotron-3-Nano-30B-A3B (NVFP4). **Configs:** A plain MCP; B router + JSON; C code mode; D router + code mode; D-oracle (gold tool list, router cost 0). Runs are serial (concurrency 1), one agent model active at a time. A scale arm (Qwen, test seed 0, 10 tasks, 42 / 200 / 2,000 tools: A, C, D) is run after the core pass.

**Hypotheses and primary comparisons (per agent):** H1 C vs A; H2 B vs A; H3 D vs C; H4 D vs B. Primary endpoint: utility U = success − 0.01 × tokens/1K − 0.002 × latency_s (router tokens and router time included for B and D); secondary: success, tokens, latency (median, trimmed mean, p90), U with λ_latency = 0.02. Paired bootstrap over task instances (10,000 resamples, 95% CI); p-values from the bootstrap; Holm correction over the 12 primary comparisons (4 per agent × 3 agents). Non-inferiority margin for H2: 2 points of success (expected to be unresolvable at this n; reported as such).

**Exclusions and failures.** A run that exceeds the 900 s cap, hangs, or errors inside the agent loop counts as a failure (success 0, latency = 900 s). Runs lost to infrastructure faults (container crash, HTTP error from the router or serving stack, wrong serving configuration) are re-run once under the identical configuration and the incident is logged; no result-dependent re-runs. Cells missing after retries are reported as missing, never imputed.

**Not tested here (stated limitations):** simulated per-call tool latency; thinking-enabled agents; real third-party MCP servers; paraphrased wording of the test tasks; security on more than one model.

---
## Extension protocol (written 2026-11-13 17:04 UTC, AFTER the confirmatory run on test seeds 0-2 was completed and analysed, BEFORE any extension run)
Motivation (review of the first draft): (a) the confirmatory run used 119 instances although this file asks for >= ~300 task-seed pairs per arm, (b) the title claim about stub return-shape hints was only tested on development seeds, (c) bootstrap should respect clustering by task family. These extension analyses are **not** part of the 12-comparison Holm family above and are labelled as extensions everywhere. Frozen configuration unchanged (tag confirmatory-freeze-v1), same flags, serial, one run per cell, same hang rule.

**Ext-1 (stub ablation on the test split).** Code mode C WITHOUT return-shape hints (no --stub-returns), test seeds 0-2 (119 instances), all three agents, paired against the already-run hinted C. Endpoints: success difference and U difference (hinted minus unhinted). Paired family-cluster bootstrap, Holm over the 3 agents.
**Ext-2 (replication of H3 with more instances).** NEW test instances: salt test, seeds 3-5, size medium (119 instances; verified solvable and deterministic before any run, 0 failures), configs C, D/mcprouter/code, D/oracle/code, all three agents. Primary: H3 (D minus C, utility U lambda_l = 0.002) per agent pooled over test seeds 0-5 (238 instances), family-cluster bootstrap (10,000 resamples), Holm over the 3 pooled tests; seeds 3-5 alone reported as the out-of-sample replication. Also reported for ALL original comparisons: family-cluster bootstrap intervals and a lambda sensitivity grid (lambda_t in {0.005, 0.01, 0.02}, lambda_l in {0, 0.002, 0.02}) computed from existing traces (no new runs).
Nothing else will be run or analysed under this extension. Results will be reported whatever they show.
