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
