"""Extension analyses (PREREG 'Extension protocol'). Usage: python bench/confirm_robustness.py traces/confirmatory
1. Family-cluster bootstrap (resample task FAMILIES with replacement, keep all instances of a family) for the 12 original primary comparisons, Holm over 12.
2. lambda sensitivity grid for the original comparisons (point estimate and cluster-CI significance).
3. Ext-1: hinted minus unhinted code mode on test seeds 0-2 (if ext1 files exist), Holm over the 3 agents.
4. Ext-2: H3 (D minus C) per agent pooled over test seeds 0-5 and on seeds 3-5 alone (if ext2 files exist), Holm over the 3 pooled tests.
Cells missing in any compared config are dropped from that comparison."""
import json, os, sys, random, collections
d = sys.argv[1] if len(sys.argv) > 1 else "traces/confirmatory"; random.seed(20261113); B = 10000
AG = ["qwen", "gemma", "nemotron"]; D = "D/mcprouter/code"; BJ = "B/mcprouter"
def U(m, ll=0.002, lt=0.01): return m["success"] - lt * m.get("total_tokens", 0) / 1000 - ll * m.get("latency_s", 0)
def load(f):
    by = collections.defaultdict(dict)
    if os.path.exists(f):
        for l in open(f):
            r = json.loads(l); by[r["config"]][(r["task_id"], r["world_seed"])] = r
    return by
def merge(*bys):
    out = collections.defaultdict(dict)
    for b in bys:
        for c, v in b.items(): out[c].update(v)
    return out
def cboot(items):
    """items: list of (family, diff). Cluster bootstrap over families. Returns mean diff, lo, hi, two-sided p."""
    fam = collections.defaultdict(list)
    for f, x in items: fam[f].append(x)
    cl = list(fam.values()); n = sum(len(c) for c in cl); m = sum(sum(c) for c in cl) / n
    sums = [(sum(c), len(c)) for c in cl]; bs = []
    for _ in range(B):
        pick = random.choices(sums, k=len(sums)); bs.append(sum(a for a, _ in pick) / sum(b for _, b in pick))
    bs.sort(); p = 2 * min(sum(1 for b in bs if b <= 0), sum(1 for b in bs if b >= 0)) / B
    return m, bs[int(B * .025)], bs[int(B * .975)], max(p, 1 / B)
def diffs(by, a, b, fn):
    keys = sorted(set(by[a]) & set(by[b])); return [(by[a][k]["family"], fn(by[a][k]["metrics"]) - fn(by[b][k]["metrics"])) for k in keys], len(keys)
def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i]); adj = [0] * len(ps); run = 0; m = len(ps)
    for rank, i in enumerate(order): run = max(run, min(1, (m - rank) * ps[i])); adj[i] = run
    return adj
out = []; core = {ag: load(f"{d}/test_{ag}_core.jsonl") for ag in AG}
COMP = (("H1 C-A", "C", "A"), ("H2 B-A", BJ, "A"), ("H3 D-C", D, "C"), ("H4 D-B", D, BJ))
# 1. cluster bootstrap, original 12
rows = []
for ag in AG:
    for nm, a, b in COMP:
        it, n = diffs(core[ag], a, b, U); r = cboot(it); rows.append((ag, nm, n, len({f for f, _ in it}), r))
adj = holm([r[4][3] for r in rows])
out.append("## 1. Original 12 comparisons, family-cluster bootstrap (U, lambda_l=0.002; Holm over 12)\n| agent | comparison | n inst | n families | dU | 95% cluster CI | raw p | Holm p | sig |\n|---|---|---|---|---|---|---|---|---|")
for (ag, nm, n, nf, r), a in zip(rows, adj): out.append(f"| {ag} | {nm} | {n} | {nf} | {r[0]:+.3f} | [{r[1]:+.3f},{r[2]:+.3f}] | {r[3]:.4f} | {a:.4f} | {'yes' if a < .05 else 'no'} |")
# 2. lambda grid
out.append("\n## 2. Lambda sensitivity (dU point estimate; * = family-cluster 95% CI excludes 0, unadjusted)\n| agent | comparison | " + " | ".join(f"lt={lt},ll={ll}" for lt in (0.005, 0.01, 0.02) for ll in (0, 0.002, 0.02)) + " |\n|---|---|" + "---|" * 9)
for ag in AG:
    for nm, a, b in COMP:
        cells = []
        for lt in (0.005, 0.01, 0.02):
            for ll in (0, 0.002, 0.02):
                it, n = diffs(core[ag], a, b, lambda m: U(m, ll, lt)); r = cboot(it); cells.append(f"{r[0]:+.3f}{'*' if (r[1] > 0 or r[2] < 0) else ''}")
        out.append(f"| {ag} | {nm} | " + " | ".join(cells) + " |")
# 3. Ext-1
e1 = []
for ag in AG:
    un = load(f"{d}/ext1_{ag}_unhinted.jsonl")
    if "C" not in un: continue
    by = {"H": core[ag]["C"], "N": un["C"]}; merged = collections.defaultdict(dict); merged["H"], merged["N"] = by["H"], by["N"]
    for nm, fn in (("success", lambda m: m["success"]), ("U", U), ("tokens", lambda m: m.get("total_tokens", 0))):
        it, n = diffs(merged, "H", "N", fn); r = cboot(it); e1.append((ag, nm, n, r))
if e1:
    pU = [x[3][3] for x in e1 if x[1] == "U"]; adjU = dict(zip([x[0] for x in e1 if x[1] == "U"], holm(pU)))
    out.append("\n## 3. Ext-1: stub return-shape hints on the test split (hinted minus unhinted code mode, test seeds 0-2; family-cluster bootstrap; Holm over 3 agents on U)\n| agent | metric | n | hinted - unhinted | 95% cluster CI | raw p | Holm p (U only) |\n|---|---|---|---|---|---|---|")
    for ag, nm, n, r in e1: out.append(f"| {ag} | {nm} | {n} | {r[0]:+.3f} | [{r[1]:+.3f},{r[2]:+.3f}] | {r[3]:.4f} | {adjU[ag]:.4f} |" if nm == "U" else f"| {ag} | {nm} | {n} | {r[0]:+.3f} | [{r[1]:+.3f},{r[2]:+.3f}] | {r[3]:.4f} | |")
# 4. Ext-2
e2 = []
for ag in AG:
    new = load(f"{d}/ext2_{ag}_s345.jsonl")
    if D not in new or "C" not in new: continue
    pooled = merge(core[ag], new)
    for lab, by in (("seeds 0-5 pooled", pooled), ("seeds 3-5 only", new)):
        for nm, a, b in (("H3 D-C", D, "C"), ("ref D-oracle - C", "D/oracle/code", "C")):
            if a in by and b in by:
                it, n = diffs(by, a, b, U); r = cboot(it); itS, _ = diffs(by, a, b, lambda m: m["success"]); rs = cboot(itS); e2.append((ag, lab, nm, n, r, rs))
if e2:
    pp = [x[4][3] for x in e2 if x[1].startswith("seeds 0-5") and x[2] == "H3 D-C"]; ids = [x[0] for x in e2 if x[1].startswith("seeds 0-5") and x[2] == "H3 D-C"]; ad = dict(zip(ids, holm(pp)))
    out.append("\n## 4. Ext-2: H3 with more instances (family-cluster bootstrap; Holm over the 3 pooled H3 tests)\n| agent | sample | comparison | n | dU | 95% cluster CI | raw p | Holm p (pooled H3) | d success [CI] |\n|---|---|---|---|---|---|---|---|---|")
    for ag, lab, nm, n, r, rs in e2:
        h = f"{ad[ag]:.4f}" if (lab.startswith("seeds 0-5") and nm == "H3 D-C") else ""
        out.append(f"| {ag} | {lab} | {nm} | {n} | {r[0]:+.3f} | [{r[1]:+.3f},{r[2]:+.3f}] | {r[3]:.4f} | {h} | {rs[0]:+.3f} [{rs[1]:+.3f},{rs[2]:+.3f}] |")
open(f"{d}/robustness.md", "w").write("\n".join(out)); print("\n".join(out))
