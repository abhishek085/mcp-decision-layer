"""Pre-specified confirmatory analysis (PREREG confirmatory protocol). Usage: python bench/confirm_analysis.py traces/confirmatory
Primary endpoint U = success - 0.01*tokens/1K - 0.002*latency_s (router tokens/time already included for B and D);
secondary: success, tokens, latency (mean/median/trimmed/p90), U with lambda_latency=0.02.
Primary comparisons per agent: H1 C-A, H2 B-A, H3 D-C, H4 D-B (D = D/mcprouter/code, B = B/mcprouter). Paired bootstrap over task instances,
10,000 resamples, 95% CI, two-sided bootstrap p, Holm over the 12 primary comparisons. D-oracle is reported as a reference, not a primary test.
Cells missing in any compared config are dropped from that comparison and counted; nothing is imputed."""
import json, os, sys, random, statistics, collections
sys.path.insert(0, ".")
d = sys.argv[1] if len(sys.argv) > 1 else "traces/confirmatory"; random.seed(20261112); B = 10000
AG = ["qwen", "gemma", "nemotron"]; CF = ["A", "B/mcprouter", "C", "D/mcprouter/code", "D/oracle/code"]
def U(m, ll=0.002, lt=0.01): return m["success"] - lt * m.get("total_tokens", 0) / 1000 - ll * m.get("latency_s", 0)
def load(f):
    by = collections.defaultdict(dict)
    for l in open(f):
        r = json.loads(l); by[r["config"]][(r["task_id"], r["world_seed"])] = r   # last row wins
    return by
def boot(x):
    n = len(x); m = sum(x) / n; bs = sorted(sum(random.choices(x, k=n)) / n for _ in range(B))
    p = 2 * min(sum(1 for b in bs if b <= 0), sum(1 for b in bs if b >= 0)) / B
    return m, bs[int(B * .025)], bs[int(B * .975)], max(p, 1 / B)
def pct(v, q): v = sorted(v); return v[min(len(v) - 1, int(len(v) * q))]
prim = []; out = []
for ag in AG:
    f = f"{d}/test_{ag}_core.jsonl"
    if not os.path.exists(f): out.append(f"## {ag}: no data\n"); continue
    by = load(f); out.append(f"## {ag}\n")
    out.append("| config | n | success | tokens | latency mean | median | trimmed | p90 | U(.002) | U(.02) | hang/err |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for c in CF:
        rs = list(by.get(c, {}).values()); n = len(rs)
        if not n: continue
        lat = [r["metrics"].get("latency_s", 0) for r in rs]; tl = sorted(lat)[int(n * .05): n - int(n * .05)]
        out.append(f"| {c} | {n} | {sum(r['metrics']['success'] for r in rs)/n:.3f} | {sum(r['metrics'].get('total_tokens',0) for r in rs)/n:.0f} | {statistics.mean(lat):.1f} | {statistics.median(lat):.1f} | {statistics.mean(tl):.1f} | {pct(lat,.9):.1f} | "
                   f"{sum(U(r['metrics']) for r in rs)/n:.3f} | {sum(U(r['metrics'],.02) for r in rs)/n:.3f} | {sum(1 for r in rs if r.get('synthetic_hang_failure'))}/{sum(1 for r in rs if r.get('error'))} |")
    out.append("")
    for name, a, b in (("H1 C-A", "C", "A"), ("H2 B-A", "B/mcprouter", "A"), ("H3 D-C", "D/mcprouter/code", "C"), ("H4 D-B", "D/mcprouter/code", "B/mcprouter"), ("ref D-oracle minus C", "D/oracle/code", "C")):
        if a not in by or b not in by: continue
        keys = sorted(set(by[a]) & set(by[b])); res = {}
        for mn, fn in (("U(.002)", lambda r: U(r["metrics"])), ("U(.02)", lambda r: U(r["metrics"], .02)), ("success", lambda r: r["metrics"]["success"]),
                       ("tokens", lambda r: r["metrics"].get("total_tokens", 0)), ("latency_s", lambda r: r["metrics"].get("latency_s", 0))):
            res[mn] = boot([fn(by[a][k]) - fn(by[b][k]) for k in keys])
        out.append(f"- **{name}** (n={len(keys)} matched cells): " + "; ".join(f"{k} {v[0]:+.3f} [{v[1]:+.3f},{v[2]:+.3f}]" for k, v in res.items()) + f"; p(U)={res['U(.002)'][3]:.4f}")
        if not name.startswith("ref"): prim.append((ag, name, res["U(.002)"][3], res["U(.002)"]))
    out.append("")
# Holm over the primary comparisons present
out.append("## Holm correction over primary comparisons (endpoint U, lambda_l=0.002)\n| agent | comparison | dU | 95% CI | raw p | Holm-adjusted p | significant at 0.05 |\n|---|---|---|---|---|---|---|")
srt = sorted(prim, key=lambda x: x[2]); m = len(srt); run = 0
for i, (ag, nm, p, r) in enumerate(srt):
    run = max(run, min(1, (m - i) * p)); out.append(f"| {ag} | {nm} | {r[0]:+.3f} | [{r[1]:+.3f},{r[2]:+.3f}] | {p:.4f} | {run:.4f} | {'yes' if run < .05 else 'no'} |")
out.append(f"\n(m = {m} primary comparisons present; the protocol fixes m = 12 when all three agents are complete.)")
# scale arm
out.append("\n## Scale arm (Qwen, test seed 0, 10 tasks)\n| catalog | config | n | success | tokens | latency mean | median | p90 |\n|---|---|---|---|---|---|---|---|")
tasks = None; core = f"{d}/test_qwen_core.jsonl"
for nd, f in ((42, core), (200, f"{d}/test_qwen_scale_n158.jsonl"), (2000, f"{d}/test_qwen_scale_n1958.jsonl")):
    if not os.path.exists(f): continue
    by = load(f)
    for c in ("A", "C", "D/mcprouter/code"):
        rs = [r for (t, s), r in by.get(c, {}).items() if s == 0 and (nd != 42 or t in __import__("bench.confirm_driver", fromlist=["x"]).SCALE_TASKS)] if nd == 42 else list(by.get(c, {}).values())
        if not rs: continue
        lat = [r["metrics"].get("latency_s", 0) for r in rs]; n = len(rs)
        out.append(f"| {nd} | {c} | {n} | {sum(r['metrics']['success'] for r in rs)/n:.2f} | {sum(r['metrics'].get('total_tokens',0) for r in rs)/n:.0f} | {statistics.mean(lat):.1f} | {statistics.median(lat):.1f} | {pct(lat,.9):.1f} |")
open(f"{d}/analysis.md", "w").write("\n".join(out)); print("\n".join(out))
