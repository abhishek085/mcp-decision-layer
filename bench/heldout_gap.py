"""Held-out shape-routing test. Labels (best shape per task family / per task id) are learned on TRAIN seeds and applied to TEST seeds
(fresh world instances, never seen). Also reports the in-sample test oracle for reference (optimistic)."""
import json, sys, collections, random
sys.path.insert(0, ".")
from bench.oracle_gap import U, load
LT, LL = 0.01, 0.0
def cells(files, sut, seeds):
    d = load(files, sut); return {k: v for k, v in d.items() if k[1] in seeds}
def main(sut, train_files, test_files, train_seeds, test_seeds):
    tr, te = cells(train_files, sut, train_seeds), cells(test_files, sut, test_seeds)
    from tasks.templates import build_suite
    from worlds.world import World
    fam = {}
    for s in set(train_seeds) | set(test_seeds):
        for t in build_suite(World(s, "medium", "dev")): fam[(t.id, s)] = t.family
    def u(c, cfg): return U(c[cfg]["metrics"], LT, LL)
    # labels
    by_fam = collections.defaultdict(lambda: [0.0, 0.0]); by_id = collections.defaultdict(lambda: [0.0, 0.0])
    for (tid, s), c in tr.items():
        f = fam.get((tid, s))
        for lab, key in ((by_fam, f), (by_id, tid)):
            lab[key][0] += u(c, "A"); lab[key][1] += u(c, "C")
    pick = lambda tab, key: ("C" if tab[key][1] >= tab[key][0] else "A") if key in tab else None
    keys = sorted(te); n = len(keys)
    allC = sum(u(te[k], "C") for k in keys) / n; allA = sum(u(te[k], "A") for k in keys) / n; best = max(allA, allC)
    def route(tab, which):
        tot = 0; miss = 0
        for k in keys:
            key = fam.get(k) if which == "fam" else k[0]
            p = pick(tab, key)
            if p is None: p = "C" if allC >= allA else "A"; miss += 1
            tot += u(te[k], p)
        return tot / n, miss
    rf, mf = route(by_fam, "fam"); ri, mi = route(by_id, "id")
    orc = sum(max(u(te[k], "A"), u(te[k], "C")) for k in keys) / n
    random.seed(0)
    def boot(f):
        xs = [f(k) for k in keys]; bs = sorted(sum(random.choices(xs, k=n)) / n for _ in range(5000)); return sum(xs) / n, bs[125], bs[4875]
    bestfix = "C" if allC >= allA else "A"
    print(f"SUT={sut} train seeds {train_seeds} -> test seeds {test_seeds}: {n} held-out cells (U with lambda_t={LT}, no latency)")
    print(f"always-A {allA:.3f} | always-C {allC:.3f} | family-label router {rf:.3f} (unseen {mf}) | task-id router {ri:.3f} (unseen {mi}) | test-oracle (in-sample, biased) {orc:.3f}")
    for name, tab, which in (("family router", by_fam, "fam"), ("task-id router", by_id, "id")):
        def d(k, tab=tab, which=which):
            key = fam.get(k) if which == "fam" else k[0]; p = pick(tab, key) or bestfix
            return u(te[k], p) - u(te[k], bestfix)
        m, lo, hi = boot(d); print(f"  {name} minus best-fixed({bestfix}): {m:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]")
    print(f"  label agreement fam-vs-oracle on test: {sum(1 for k in keys if (pick(by_fam, fam.get(k)) or bestfix) == ('C' if u(te[k],'C')>=u(te[k],'A') else 'A'))/n:.2f}")
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("sut"); ap.add_argument("--train", nargs="+"); ap.add_argument("--test", nargs="+")
    ap.add_argument("--train-seeds", type=int, nargs="+", default=[0, 1, 2]); ap.add_argument("--test-seeds", type=int, nargs="+", default=[3, 4, 5])
    a = ap.parse_args(); main(a.sut, a.train, a.test, a.train_seeds, a.test_seeds)
