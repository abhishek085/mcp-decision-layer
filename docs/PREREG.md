# PREREG (written 2026-10-22, AFTER the A-vs-C pilot v1/v2 on Qwen — a deviation from plan Phase 0; see EXPERIMENT_LOG E4.1/E4.2)
Everything below applies to results produced AFTER this commit. Pilot v1/v2 A-vs-C results are exploratory.

Hypotheses: H1..H6 as in plan Sec 1.
Primary metrics: success, total tokens, latency, U = success − λt·(tokens/1000) − λl·latency_s. Primary λ pair: λt = 0.01, λl = 0.002 (chosen before seeing D/B results; a grid is also reported).
Margins: success non-inferiority 2 pp (note pilot n=36 pairs cannot resolve this; confirmatory runs need ≥ ~300 task-seed pairs per arm). Minimum effect on U: 0.03 (≈ 3 pp success or 3K tokens at primary λ).
Gate (Phase 6): proceed to training only if oracle(U over {A,C}) − max(always-A, always-C) > 0.03 AND the best rule captures < 60% of that gap.
Tool recall threshold (Phase 5): ≥ 0.95 at catalog size 20 and ≥ 0.90 at 200.
Sample sizes: pilot = 18 tasks × 3 seeds; dev and sealed test sets are NOT yet built (tasks use World(salt="dev")); sealed test will use salt="test" and be opened once.
Analysis: paired bootstrap (5,000+ resamples), Holm correction over H1–H6, ablations per plan 11.3.
Exclusions: runs with infrastructure errors (logged, counted separately). Tasks failing the solver check.
Thinking mode: pilots use Qwen thinking OFF (enable_thinking=false); a thinking-ON subset is a pre-declared robustness arm.
Latency: only from serial passes (concurrency 1, no other SUT active), see E1.3.
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
