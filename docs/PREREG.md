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
