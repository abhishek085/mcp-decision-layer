import json, sys, collections, random
R = [json.loads(l) for l in open(sys.argv[1])]
seeds = sorted({r["world_seed"] for r in R}); cfgs = sorted({r["config"] for r in R})
def agg(rs, k): return sum(r["metrics"].get(k, 0) for r in rs) / max(len(rs), 1)
for sel, name in [(lambda r: True, "ALL seeds"), (lambda r: r["world_seed"] != 0, "fresh seeds (1,2) only")]:
    print("##", name)
    for c in cfgs:
        rs = [r for r in R if r["config"] == c and sel(r)]
        print(f" {c}: n={len(rs)} success={agg(rs,'success'):.3f} tokens={agg(rs,'total_tokens'):.0f} schema={agg(rs,'schema_tokens'):.0f} backend_result_tok={agg(rs,'backend_result_tokens'):.0f} ctx_result_tok={agg(rs,'result_tokens'):.0f} lat={agg(rs,'latency_s'):.1f}s err={sum(1 for r in rs if r['error'])}")
print("## by family (success A/C, tokens A/C)")
fam = sorted({r["family"] for r in R})
for f in fam:
    row = []
    for c in cfgs:
        rs = [r for r in R if r["family"] == f and r["config"] == c]
        row.append(f"{c}: {agg(rs,'success'):.2f} / {agg(rs,'total_tokens'):.0f}")
    print(f" {f:12}", " | ".join(row))
# paired bootstrap C-A on fresh seeds, per (task,seed)
def paired(metric, sel):
    d = collections.defaultdict(dict)
    for r in R:
        if sel(r): d[(r["task_id"], r["world_seed"])][r["config"]] = r["metrics"].get(metric, 0)
    xs = [v["C"] - v["A"] for v in d.values() if "A" in v and "C" in v]
    random.seed(0); bs = sorted(sum(random.choices(xs, k=len(xs))) / len(xs) for _ in range(5000))
    return sum(xs) / len(xs), bs[125], bs[4875], len(xs)
for m in ["success", "total_tokens"]:
    print(f"paired C-A {m} (fresh seeds): mean=%.3f CI95=[%.3f, %.3f] n=%d" % paired(m, lambda r: r["world_seed"] != 0))
