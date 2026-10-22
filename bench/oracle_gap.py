"""Phase 6: oracle gap between always-A, always-C, rule-based shape, and per-task oracle. U = success - lt*tokens/1000 - ll*latency_s."""
import json, sys, itertools, collections, random
sys.path.insert(0, ".")
from gateway.router import shape_features
from worlds.world import World
from tasks.templates import build_suite
LT, LL = 0.01, 0.002
def U(m, lt=LT, ll=LL): return m["success"] - lt * m.get("total_tokens", 0) / 1000 - ll * m.get("latency_s", 0)

def load(files, sut):
    R = [json.loads(l) for f in files for l in open(f)]
    R = [r for r in R if r["sut"] == sut and r["config"] in ("A", "C") and r.get("n_dist", 0) == 0]
    d = collections.defaultdict(dict)
    for r in R: d[(r["task_id"], r["world_seed"])][r["config"]] = r
    return {k: v for k, v in d.items() if "A" in v and "C" in v}

def rule_pick(text, q, F, C):
    f = shape_features(text, []); return "C" if ((q and f["quant"]) or f["maxnum"] >= F or f["chain"] >= C) else "A"

def analyse(files, sut, lt, ll, label):
    d = load(files, sut); texts = {}
    for seed in {k[1] for k in d}:
        for t in build_suite(World(seed, "medium", "dev")): texts[(t.id, seed)] = (t.instruction, t.factors, t.family)
    keys = sorted(k for k in d if k in texts)
    u = {k: {c: U(d[k][c]["metrics"], lt, ll) for c in "AC"} for k in keys}
    grid = list(itertools.product([0, 1], [3, 5, 10, 20, 999], [1, 2, 999]))
    def score(ks, p): return sum(u[k][rule_pick(texts[k][0], *p)] for k in ks) / len(ks)
    seeds = sorted({k[1] for k in keys}); rule_u = {}
    for s in seeds:                          # leave-one-seed-out: tune on others, apply to held-out seed
        tr = [k for k in keys if k[1] != s]; te = [k for k in keys if k[1] == s]
        best = max(grid, key=lambda p: score(tr, p))
        for k in te: rule_u[k] = u[k][rule_pick(texts[k][0], *best)]
    n = len(keys); A = sum(u[k]["A"] for k in keys) / n; C = sum(u[k]["C"] for k in keys) / n
    orc = sum(max(u[k].values()) for k in keys) / n; rule = sum(rule_u.values()) / n; base = max(A, C)
    gap = orc - base; cap = (rule - base) / gap if gap > 1e-9 else float("nan")
    print(f"\n## {label}  SUT={sut}  n={n} task-seed pairs  (lambda_t={lt}, lambda_l={ll})")
    print(f"mean U: always-A {A:.3f} | always-C {C:.3f} | rule(LOSO) {rule:.3f} | oracle {orc:.3f}")
    print(f"oracle gap over best fixed shape = {gap:.3f}; rule captures {cap*100:.0f}% of it; success A/C = {sum(d[k]['A']['metrics']['success'] for k in keys)/n:.3f}/{sum(d[k]['C']['metrics']['success'] for k in keys)/n:.3f}")
    wins = collections.Counter("A" if u[k]["A"] > u[k]["C"] else ("C" if u[k]["C"] > u[k]["A"] else "tie") for k in keys); print("per-task winner counts:", dict(wins))
    # by factor
    for fac in ("fanout_bin", "adapt", "servers", "size", "family"):
        grp = collections.defaultdict(list)
        for k in keys:
            F = texts[k][1]; fam = texts[k][2]
            v = {"fanout_bin": "fan1" if F["fanout"] <= 1 else ("fan2-9" if F["fanout"] < 10 else "fan10+"), "adapt": F["adapt"], "servers": F["servers"], "size": F["size"], "family": fam}[fac]
            grp[v].append(k)
        print(f" by {fac}:")
        for v, ks in sorted(grp.items(), key=lambda x: str(x[0])):
            a = sum(u[k]["A"] for k in ks) / len(ks); c = sum(u[k]["C"] for k in ks) / len(ks); o = sum(max(u[k].values()) for k in ks) / len(ks)
            print(f"   {str(v):14} n={len(ks):3}  A={a:+.3f} C={c:+.3f} oracle={o:+.3f}  gap={o-max(a,c):.3f}")
    return gap, cap

if __name__ == "__main__":
    files = sys.argv[2:]; sut = sys.argv[1]
    analyse(files, sut, 0.01, 0.002, "primary lambda"); analyse(files, sut, 0.01, 0.0, "tokens only (no latency)"); analyse(files, sut, 0.0, 0.0, "success only")
