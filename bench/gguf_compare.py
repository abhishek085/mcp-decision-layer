"""Compare per-candidate P(yes) of a GGUF variant (via llama-server + gateway) with the bf16 safetensors reference (vLLM) on the same rows."""
import json, sys, math
sys.path.insert(0, ".")
from bench.toolsel import metrics
ref = [json.loads(l) for l in open(sys.argv[1])]; tst = [json.loads(l) for l in open(sys.argv[2])]; label = sys.argv[3]
assert len(ref) == len(tst), (len(ref), len(tst))
lg = lambda p: math.log(max(p, 1e-9) / max(1 - p, 1e-9))
xs, ys, absd = [], [], []
for a, b in zip(ref, tst):
    assert a["task"] == b["task"] and a["cand"] == b["cand"]
    for n in a["cand"]:
        pa, pb = a["probs"][n], b["probs"].get(n, 0.0); xs.append(lg(pa)); ys.append(lg(pb)); absd.append(abs(pa - pb))
n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
corr = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
print(f"== {label}: {len(ref)} tasks, {n} candidate scores")
print(f"   logit correlation {corr:.4f} | mean |dP| {sum(absd)/n:.4f} | p99 |dP| {sorted(absd)[int(n*.99)]:.3f} | max |dP| {max(absd):.3f}")
for th in (0.01, 0.05, 0.3):
    agree = sum((a["probs"][c] >= th) == (b["probs"].get(c, 0) >= th) for a, b in zip(ref, tst) for c in a["cand"]) / n
    ra = [metrics([c for c in r["cand"] if r["probs"][c] >= th], r["gold"], 0) for r in ref]; rb = [metrics([c for c in r["cand"] if r["probs"].get(c, 0) >= th], r["gold"], 0) for r in tst]
    f = lambda ms, k: sum(m[k] for m in ms) / len(ms)
    print(f"   th={th}: decision agreement {agree:.4f} | complete-recall ref {f(ra,'complete'):.3f} vs gguf {f(rb,'complete'):.3f} | tools ref {f(ra,'n_sel'):.2f} vs gguf {f(rb,'n_sel'):.2f}")
