# EXPERIMENT LOG — MCP Decision Layer

Single record of everything tried: setup, commands, results, failures, deviations. Append-only; newest at bottom. Plan: `mcp-decision-layer-plan.md`.
Machine: DGX Spark (GB10, 121 GB unified memory). Executor: Claude Code (Sonnet 5.5) under user Ab.

---
## E0.1 — Environment survey (2026-10-22)
- Running at start: Qwen3.8-27B (tensorfold docker `qwen38-27b-tf`, :8888, ~52 GB GPU, 4 parallel lanes, ctx 262144); spark-s1-4b-v8-nvfp4 (docker `osj-jev-vllm` :8355, wrapped by `open_spark_jev.serve.gateway` on :8400); hermes-gateway systemd service (uses Qwen on :8888); ComfyUI not running.
- Available weights in HF cache: Gemma-4-26B-A4B-NVFP4, Gemma-4-31B-IT-NVFP4, Nemotron-3-Nano-30B-A3B-NVFP4, Nemotron-3-Super-120B (too large to co-serve), Qwen3-4B, Gemma-4-E4B-it, Llama-Guard/Prompt-Guard, deberta prompt-injection, others.
- Hermes: tried `systemctl stop hermes-gateway` → denied (needs sudo). Hermes idle (0 running requests), left running. User later offered to stop it; declined for now (no contention observed).
- Python venv `.venv` created (mcp 2.3.0, openai, httpx, numpy, scipy, tiktoken).
- No fourth-family model (Llama/Mistral/gpt-oss) served; per plan 3.3 the SUT-3/test-writer shared-family flag is therefore kept unless gpt-oss is started later (container `osj-teacher-gptoss` exists but its weights are not verified).

## E0.2 — Roster decisions (deviations from plan, Phase 0)
| Role | Model | Endpoint | Note |
|---|---|---|---|
| SUT-1 | Qwen3.8-27B (MLX 4bit via tensorfold) | :8888 | given |
| SUT-2 / train writer | Gemma-4-26B-A4B NVFP4 | :8002 (mdl-gemma) | |
| SUT-3 / test writer | Nemotron-3-Nano-30B-A3B NVFP4 | :8003 (planned) | Super-120B does not fit alongside others; flag 3.3 stays |
| SUT-S small | Qwen3-4B or Gemma-4-E4B | planned | |
| Decision | spark-s1-4b-v8-nvfp4 | :8400 | |

## E1.1 — Smoke test: Qwen3.8-27B (bench/smoke.py)
Result: function calling 10/10 correct (avg 0.81 s); script writing correct; decode 126.5 tok/s single stream, 188.7 tok/s aggregate at concurrency 8 (4 server lanes); long context: 200-tool catalog = 48,102 prompt tokens, correct tool picked, 37.6 s latency (prefill-bound, ~1.3K tok/s).
Outcome: PASS. Native function calling supported. Note 200 tools ≈ 48K tokens in this tokenizer (plan estimate 30K).

## E1.2 — spark-s1 /v1/decide probe
Request with a shape question (json/code) on a 50-item fan-out task: returns `selected`, full `probabilities` over options, confidence, margin, entropy; ~268 ms (cold). Answer: code 0.947.
Outcome: Open item "does API expose full option probabilities" = YES (via /v1/decide). Use /v1/decide (typed choice/boolean questions) rather than /v1/evaluate.
- mcp pinned to <2 (v2.3.0 renamed FastMCP; v1 API used for stability).

## E0.3 — User offer: Hermes logs as test data (2026-10-22)
User allowed using their Hermes logs as test data. Decision: NOT used in the core benchmark (traces/worlds are to be released; logs may contain personal data/secrets; not seed-reproducible). Possible later use: local-only, unreleased realism check, or log-line format only. Needs explicit go-ahead per use.

## E2.1 — World slice built (worlds/world.py)
4 real MCP servers via official SDK (FastMCP, in-memory transport): issues(5 tools), chat(4), logs(2), billing(3) = 14 tools. Seeded by (salt, seed, size); size knobs for rows/text length. Snapshot hash over mutable state. Smoke: list_tools and call_tool work over the MCP protocol; World(0,"medium") hash 24cc240781cbba76, 180 issues, 1500 log lines.
Scope note: this is a vertical slice (4 of the 12 planned servers). Free text is template-generated; the LLM-writer pass is not done yet. Both are listed deviations from plan Sec 5.

## E2.2 — Tasks + reference solvers (tasks/templates.py, tasks/check_solvable.py)
12 template families / 18 task instances per world (lookup, chain_dm, log_agg, log_scan, bill_sum, refund_cond, explore, join_agg, reminder at fan-out 1/5/15/30). Code verifiers check final state + answer.
Check: reference solver run twice on dev seeds 0 and 1 → all solvable and deterministic (identical state hash), FAILS: 0. First version had colliding reminder ids and fan-out capped at ~9 (bug-label filter); fixed to all open issues + repo in id.

## E4.0 — Gateway A and C dry run (Qwen3.8-27B, 2 tasks)
gateway/gw.py: Hub (real MCP over in-memory transport), mode A (JSON calls, all schemas, 25-turn cap), mode C (search+execute, subprocess sandbox with RPC bridge, 3 executions). Sandbox is a rlimit'd subprocess, NOT a container (deviation, TODO).
Dry run, thinking ON (server default): A 2/2, C 2/2. 14-catalog schema = 4,446 tokens (A) vs 512 (C meta tools). assignee task: A 18.3K tokens, C 5.5K. Latency 20–36 s per task, dominated by hidden reasoning tokens.
Finding: Qwen thinking is controlled with extra_body chat_template_kwargs.enable_thinking=false (0.23 s vs 0.56 s on a trivial prompt). Reasoning tokens are not in the reasoning-free count, so token comparisons must state the thinking setting. Decision (pilot): thinking OFF for throughput; thinking ON on a subset later.
Note: first no-think run still showed 3–10 s per LLM call at ~30 output tokens with 2 concurrent runs; investigating via contention test (E1.3).

## E1.3 — Cross-model contention on shared memory bandwidth (bench/contention.py) — user-requested check
| Condition | tok/s |
|---|---|
| Qwen alone (Gemma resident, idle) | 144.7 |
| Gemma alone (Qwen idle) | 28.8 |
| Qwen while Gemma serves 4 streams | 58.9 (−59%) |
| Gemma while Qwen serves 4 streams | 14.6 (−49%) |
Outcome: concurrent models share the GB10 memory bus and slow each other badly. An idle resident model costs nothing. **Policy:** keep all models resident, but only ONE SUT (plus the small spark-s1 router) active during any timed run. Latency numbers come from a serial pass (concurrency 1, nothing else active); success/token counts may use parallel runs. Never run two SUT arms simultaneously when latency is being measured. (Also means the Gemma-judging-Qwen offline batch must not overlap timed runs.)
Gemma 4 26B-A4B NVFP4 in vLLM: only ~29 tok/s single stream (Qwen tensorfold gets 145 with MTP speculative decoding), so cross-SUT latency comparisons are not like-for-like in serving stack; compare within a SUT only. 

## Git
Committed locally (dc0392d). `git push` failed: no GitHub credentials on this machine (https://github.com/abhishek085/mcp-decision-layer.git). Needs the user to configure auth; commits continue locally.

## E4.1 — Pilot v1: A vs C on Qwen3.8-27B (dev seed 0, thinking off, 18 tasks) — HARNESS BUG FOUND
Trace: traces/pilot_qwen_AC_s0_nothink_v1_harnessbug.jsonl
| | success | mean total tokens | mean latency (conc 4) |
|---|---|---|---|
| A | 17/18 (0.94) | 24,812 | 39.1 s |
| C | 10/18 (0.56) | 8,866 | 22.6 s |
Diagnosis (plan Phase 4 gate "if C cannot match A on simple tasks, fix sandbox and prompt"): 8 C failures were all sandbox errors from MY harness, not model capability: (1) sandbox wrappers accepted only keyword args while stubs showed positional signatures → `TypeError: post_message() takes 0 positional arguments`; (2) the stub text looked like code so the model pasted it into its script, redefining tools with `raise NotImplementedError`. Fix: wrappers accept positional args in schema order; stubs rendered as comment-annotated call signatures; system prompt says tools are already defined. After fix the 4 re-tested failing tasks pass (4/4).
A failures/outliers (valid, model-driven): logscan-api A=fail with 221,073 tokens (paged raw logs through context, hit turn cap); topassign-beacon A used 94,947 tokens (C: 11,179). This is the H1 effect (large intermediate results).
Caveat: the prompt/stub fix was found using dev salt, seed 0 worlds — the same worlds as pilot v1. v2 adds seeds 1 and 2 as untouched data; seed 0 numbers are tuned-on. Fix applied to C's harness only because it was a bug; A had no equivalent bug (equal-effort rule satisfied by reporting this).
Verified: bridge correctness test (list_issues + post_message through RPC) passes.

## E4.2 — Pilot v2 (A and C, seeds 0,1,2) — running
traces/pilot_qwen_AC_s012_nothink_v2.jsonl

### E4.2 results — Pilot v2, Qwen3.8-27B, thinking OFF, A vs C, 18 tasks × seeds 0,1,2 (dev salt), conc 4
Trace: traces/pilot_qwen_AC_s012_nothink_v2.jsonl · Summary script: bench/summarize.py · wall 528 s
| | n | success | mean total tokens | schema tok/run | result tok into context | latency (conc 4, NOT a clean latency number) |
|---|---|---|---|---|---|---|
| A (all seeds) | 54 | 0.926 | 15,525 | 6,093 | 1,032 | 22.0 s |
| C (all seeds) | 54 | 0.926 | 6,581 | 536 | 991 | 16.7 s |
| A (fresh seeds 1,2) | 36 | 0.917 | 10,881 | 5,475 | 841 | 15.4 s |
| C (fresh seeds 1,2) | 36 | 0.917 | 6,379 | 526 | 983 | 15.3 s |
Paired C−A on fresh seeds (n=36 task-seed pairs, bootstrap 5,000): success diff 0.000, 95% CI [−0.139, +0.139]; total tokens diff −4,502, 95% CI [−10,789, −561].
By family (success A/C; tokens A/C): log_scan 0.50/1.00, 60,456/6,418 (C wins big: raw logs paged through context in A); join_agg 1.00/0.50, 23.7K/14.8K; chain_dm, explore, lookup, refund_cond, reminder both 1.00 with C using ~30–50% fewer tokens; log_agg C uses MORE tokens (4,467 vs 3,675: server-side aggregate_logs makes JSON trivial).
Failures (all valid, model/design-driven):
- A: logscan-api fails on seeds 0,1 (25-turn cap hit / no answer while paging raw logs); billsum-Acme seed 2 wrong.
- C: topassign-cinder fails 3/3 seeds — the model spends its 3 executions printing data for inspection (exploration), then runs out before the name lookup (answers "reached the execution limit"). billsum-Fjord seed 2 wrong (summed overdue too).
Outcome (preliminary H1 evidence, one SUT, tiny sample, thinking off): C is NOT worse than A on success (non-inferiority NOT established: CI ±14 pp is far wider than the 2 pp margin) and uses fewer tokens; the benefit concentrates on large-intermediate-result tasks. The execution cap of 3 hurts exploratory tasks — a finding about the plan's turn cap, not a bug.
Limitations: n tiny; thinking off; seeds 1,2 used dev salt same as tuning world generator; latency measured at concurrency 4 with Hermes resident (invalid for H-latency claims; a serial pass is still needed); 4 servers/14 tools only (A pays 5.5K schema tokens/run vs ~30K+ at plan scale, so A looks relatively cheap here).
Prompts frozen as of commit following this entry (SYS_A / SYS_C in gateway/gw.py) — nominal Phase 4 gate; note that no equal-effort tuning of A's prompt was done beyond zero iterations.

## STATUS / NEXT (end of first session segment)
Done: Phase 0 (partial: PREREG.md NOT written yet — TODO before any further results count as confirmatory), Phase 1 (Qwen + spark-s1; Gemma partial: server up, smoke test not yet run; Nemotron not loaded due to memory), Phase 2 slice, Phase 3 slice (18 tasks, no paraphrase pipeline), Phase 4 pilot (A, C on Qwen).
Next: (1) write PREREG.md and commit; (2) Gemma smoke test; Nemotron needs memory (free RAM ~18 GB with Qwen+Gemma+spark-s1 resident; likely requires stopping mdl-gemma while it loads/runs); (3) Phase 5 mode B (spark-s1 tool selection designs) — needs more tools/distractors to be meaningful; (4) serial latency pass; (5) Phase 6 oracle gap; (6) Phase 7 D-rules; (7) Phase 8 security.

## E1.4 — Smoke test: Gemma-4-26B-A4B NVFP4 (vLLM, --tool-call-parser gemma4, ctx 65,536)
Function calling 10/10 (0.55 s avg), script writing OK, decode 30.7 tok/s single / 254.9 aggregate at c8, 200-tool catalog = 44,258 tokens, correct pick, 23 s. PASS. PREREG.md committed (late; flagged in the file).
## E4.3 — Pilot A vs C on Gemma (seeds 0,1,2, conc 8) — running

### E4.3 results — Pilot A vs C on Gemma-4-26B-A4B (SUT-2), 18 tasks × seeds 0,1,2, thinking flag passed (ignored by vLLM/Gemma), conc 8
Trace: traces/pilot_gemma_AC_s012_nothink.jsonl · Summary: traces/pilot_gemma_summary.txt · wall 307 s
| | n | success | mean tokens | schema tok | latency (conc 8, not clean) |
|---|---|---|---|---|---|
| A | 54 | 0.870 | 7,174 | 5,132 | 10.6 s |
| C | 54 | 0.815 | 6,375 | 628 | 30.4 s |
Fresh seeds only (n=36 pairs): success diff C−A −0.028, 95% CI [−0.194, +0.139]; tokens diff −2,500, CI [−8,414, +1,331] (NOT significant).
Per family: C better on log_scan (1.00 vs 0.33); C worse on join_agg (0.33 vs 0.83), bill_sum (0.33 vs 0.67), log_agg (0.67 vs 1.00; uses 3× tokens). 
Failure modes: 7+ of 10 C failures involve sandbox errors (topassign-cinder: all 3 executions error in 2 of 3 seeds) — Gemma writes buggier scripts than Qwen; A's log_scan failure (0.33) happens with only ~3.4K tokens → Gemma answers from a first page of logs rather than paging all of them (premature answer, not turn-cap exhaustion as for Qwen).
Outcome: SUT-dependent. Qwen: C ≈ A success, −41% tokens. Gemma: C slightly lower success (−5.5 pp all seeds), ~−11% tokens, much slower latency (30 s vs 11 s: sandbox retries + vLLM at 30 tok/s). Direction of the token saving is the same; magnitude and success parity are not. This is a first sign that per-SUT shape choice may matter (relevant to Phase 6 oracle gap). Not confirmatory.
- Push works via: git -c credential.helper='!gh auth git-credential' push origin main (gh is authenticated as abhishek085). Earlier push failures were only the missing credential helper.

## E2.3 — World extended to 12 servers / 42 tools (user go-ahead: "servers then the rest")
Added servers: docs(4), calendar_email(4), crm(3), files(3), deployments(3), hr(3), inventory(4), support(4) to the original issues(5), chat(4), logs(2), billing(3) = 12 servers, 42 tools (plan target was ~120 tools; fewer executable tools, distractors supply scale). Extension entities use a separate RNG stream (`{salt}-{seed}-ext`) so the original entities for a given seed are unchanged. Snapshot hashes DO change for all seeds (state now includes the new entities) — pilot v1/v2 traces carry the old hashes.
Org chain: first 22 users form a manager chain so chain-depth tasks of 6/12/20 are possible.
Schema tokens for all 42 tools (A, OpenAI tool format) ≈ see E4.4.

## E3.1 — Task suite v2 (tasks/templates.py + templates2.py) 
23 new task instances over 12 families (rollback, restock, crm_update, ticket_email, chain_deep d=6/12/20, doc_search, doc_append, file_sum, cal_cond, ticket_triage, cross3, explore2). Factor coverage now: depth 1–20, fan-out 1–~36 (≈70 on size=large), size small/med/large, adaptivity fixed/conditional/exploratory, 1–3 servers.
QA filter in build_suite (plan 6.2 step 4): drops tasks where a no-op passes (empty target set; found: crm-ent-trial seed 0, escalate-* on some seeds) and tasks the reference solver cannot complete. Result: 39–41 kept of 41 per world; solver determinism check (identical state hash on two runs) on dev seeds 0,1,2 medium and seed 0 large: FAILS 0.
Not yet done: LLM paraphrase + cross-family verifier pass (needs Nemotron/Gemma writer; tasks currently use template phrasing only), near-duplicate filter between splits.

## E2.4 — Distractor catalog (worlds/distractors.py) 
Real tool definitions from huggingface.co/datasets/automatelab/mcp-servers-tool-catalog (CC-BY-4.0; 9,922 tools, 228+ source servers). Selection: seed 20251022, dedup by name, excluding our 42 names, 2,000 tools stored in worlds/distractors/catalog_2000.jsonl (nested: first N = N-tool arm). Served by a real low-level MCP server whose calls return `{"error":"unavailable..."}`. Raw parquet gitignored; attribution: automatelab, CC-BY-4.0.
Catalog-size arms (executable 42 + distractors): 42 / 200 (158) / 2,000 (1,958). Plan said 20/200/2000; own tool count is 42 so the smallest arm is 42.
Measured schema size in OpenAI tool format: 158 distractors = 41,550 tokens; 1,958 = 510,733 tokens. Real descriptions are far longer than the plan's estimate (200 tools ≈ 47K tokens, 2,000 ≈ 534K tokens).
=> Mode A at 2,000 tools cannot run on any available model (Qwen ctx 262K, Gemma 65K): recorded as `ctx_overflow` failure (success 0, tokens 0) via a guard in gateway/gw.py; at 200 tools A fits Qwen only.

## E4.4 — Scale probe, Qwen, 3 tasks (assignee, chain, reminder-5)
- A @200 tools: 2/2 success on the two tasks tried, but 142–190K total tokens per task, 47,288 schema tokens PER TURN, latency 190–225 s (at conc 4 with other loads; indicative only). A @2000: ctx_overflow (533,817 schema tokens).
- C @200 and @2000: first attempt 0/2 ALL sandbox SyntaxErrors — harness bug #3: sandbox defined wrapper functions for every tool in the catalog; real tool names contain hyphens / shadow Python builtins; script passed via `-c` also exceeded the OS arg limit at 2000 tools ("Argument list too long"). Fixes: wrappers only for tools the model discovered via search(), python-safe aliases (pyname), script via temp file, IDF-weighted search with name boosting (replaced raw substring counting).
- After fix C @200: 3/3 success, 11.8K tokens/task; C @2000: 3/3, 9.7K tokens/task, ~17 s each.
Outcome: scale favours C strongly (A 166K tokens @200, impossible @2000, C ≈ flat ~10K). This is H1 at scale — only on 3 tasks; to be confirmed in the scale arm.

## E5.1 — Phase 5: tool-subset selection, catalog = 42 tools (bench/toolsel.py, bench/toolsel_report.py), dev seed 0, 39 tasks, offline (no SUT)
Report: traces/toolsel_n0_report.txt · raw: traces/toolsel_dev_n0_s0.jsonl. Gold = task.needed_tools (template-declared; "enabling" tools like lookup_user are included, solutions using alternative tools would count as misses — gold noise accepted).
Designs: (c) one boolean "does completing this task require tool X (desc)?" per tool via spark-s1 /v1/decide; (b) server-level boolean first (12 servers) then tool-level; (a) embedding (bge-small-en-v1.5 via fastembed) top-30 → spark-s1 booleans; embedding-only top-k; prompted Gemma-4-26B router (JSON list of names). Threshold θ on P(true).
Selected rows (complete-recall = all gold tools present; n_sel = tools exposed):
| method | complete-recall | frac-recall | n_sel | extra |
|---|---|---|---|---|
| (c) spark per-tool θ=0.002 | 0.949 | 0.974 | 16.2 | 14.2 |
| (c) θ=0.01 | 0.846 | 0.923 | 8.4 | 6.5 |
| (c) θ=0.05 | 0.590 | 0.791 | 3.7 | 2.1 |
| (c) θ=0.3 | 0.359 | 0.641 | 1.7 | 0.3 |
| (b) server≥0.1 then tool≥0.01 | 0.410 | 0.654 | 4.1 | 2.7 |
| (a) embed30→spark θ=0.002 | 0.949 | 0.974 | 12.3 | 10.2 |
| embed-only top-12 | 0.923 | 0.966 | 12 | 10 |
| embed-only top-20 | 0.974 | 0.987 | 20 | 17.9 |
| prompted Gemma router | 0.974 | 0.991 | 2.4 | 0.4 |
Latency/task: spark per-tool 1.26 s (42 questions), two-stage 0.44 s (server stage only), embed→spark 0.91 s, Gemma router 0.77 s (Gemma alone on machine).
Findings (negative for the decision model as zero-shot tool selector on this task shape):
1. spark-s1 zero-shot is poorly calibrated for "is this tool needed?": at sensible thresholds (0.1–0.5) complete-recall is only 0.31–0.46. To reach the pre-registered recall ≥0.95 needs θ≈0.002, which exposes ~12–16 tools — no better than embedding-only top-12/20. Misses are dominated by enabling tools not named in the task: lookup_user (4), list_issues (4), list_docs, list_files...: the model scores direct relevance, not multi-step dependencies.
2. Server-level gating (design b) is worst — it compounds errors (recall 0.41).
3. A prompted LLM router from a different family (Gemma, same Qwen-agnostic) beats every spark-s1 design: 0.974 recall with only 2.4 tools. 
4. Pre-registered recall threshold (≥0.95 at the smallest catalog): spark-s1 designs meet it only by exposing 12–16 tools. => per plan Phase 5 gate: "plan a tool-subset fine-tune" is indicated; for the end-to-end B/D pilots run both B-spark (design (a), θ chosen on dev for recall≥0.95) and B-llm (Gemma router).
Caveats: single seed, tasks' wording is template-like; thresholds chosen on same data they are reported on (dev tuning, optimistic); 39 tasks → recall CI roughly ±0.15.

## E4.5 — Gateway extended with modes B and D (gateway/gw.py refactor, gateway/router.py)
json_phase / code_phase composed: B = JSON loop over a router-chosen subset + `request_more_tools` escape hatch (adds next 10 by embedding rank); D = subset + shape (json|code); code failures (sandbox error, exec limit, no clean answer) fall back to the JSON phase with a note about possible partial side effects (logged as `fallback` step with cause). Router overhead (tokens, ms) is added to total_tokens and latency. Config strings in bench/run.py: `A`, `C`, `B/<selector>`, `D/<selector>/<shape>` with selector ∈ {spark_a, llm, embed<k>, oracle, all}, shape ∈ {rules, spark, json, code, oracle}.
Smoke (Qwen, 3 tasks): B/spark_a 2/3, D/spark_a/rules 3/3, D/llm/spark 3/3. Observation: at θ=0.002 spark_a exposes ~30 of the 30 embedding candidates (degenerate: probabilities almost never below 0.002), so it is effectively "embedding top-30" — consistent with E5.1's finding.
Note: the 'llm' selector calls Gemma while a Qwen SUT is running → latency of those runs includes cross-model contention (E1.3); latency to be taken from the serial pass only.

## E6.0 — Phase 6 data collection (running): A and C, Qwen, 39-task suite × seeds 0,1,2 (dev salt, medium), thinking off, conc 4
traces/p6_qwen_AC_s012.jsonl

## E0.4 — Thermal incident (2026-10-22 ~08:35 UTC) 
Symptom: toolsel (200-tool) run stalled; `osj-jev-vllm` showed `Up (Paused)`. Cause: the user's own `thermal_guard.sh` (running since Oct 03) does `docker pause osj-*` at ≥91 °C and unpauses below 85 °C (both GPU and SoC sensors). Sensors: SoC thermal zones read 92–93 °C while Qwen served 4 concurrent streams + spark-s1 + Gemma router calls (GPU 82–83 °C). 92–95 °C is the machine's protective-throttle/shutdown range.
Action: I did NOT touch the guard or unpause manually. I killed my own jobs (toolsel 158 run; p6 Qwen A/C run, 15 of 234 runs done, partial file traces/p6_qwen_AC_s012.jsonl to be discarded/re-run). Idle cooldown: 93 → 64 °C within ~30 s; guard unpaused spark-s1 automatically.
Mitigation: gateway/thermal.py self-throttle (no new run/router call while any thermal zone ≥ 86 °C); concurrency kept ≤ 3 for Qwen. Consequence: wall-clock for long runs is longer; latencies taken during hot periods are unreliable.
