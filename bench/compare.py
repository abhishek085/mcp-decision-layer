"""Matched comparison of configs on the same (task, seed) cells; paired bootstrap CIs vs a reference config."""
import json, sys, random, collections
LT, LL = 0.01, 0.002
def U(m, ll=LL): return m["success"] - LT * m.get("total_tokens", 0) / 1000 - ll * m.get("latency_s", 0)
def main(sut, files, ref="C"):
    R = [json.loads(l) for f in files for l in open(f)]
    R = [r for r in R if r["sut"] == sut and r.get("n_dist", 0) == 0]
    import os
    if os.environ.get('HINTED_CODE'):   # keep only hinted rows for code-using configs (C, D/*); A and B are JSON so unaffected
        R = [r for r in R if not (r['config'] == 'C' or r['config'].startswith('D/')) or r.get('stub_returns')]
    cell = collections.defaultdict(dict)
    for r in R: cell[(r["task_id"], r["world_seed"])][r["config"]] = r          # last wins
    cfgs = sorted({c for v in cell.values() for c in v}); common = [k for k, v in cell.items() if all(c in v for c in cfgs)]
    print(f"SUT={sut}: {len(common)} cells common to all {len(cfgs)} configs: {cfgs}\n")
    random.seed(0)
    def boot(xs): 
        bs = sorted(sum(random.choices(xs, k=len(xs))) / len(xs) for _ in range(5000)); return bs[125], bs[4875]
    print(f"{'config':20}{'success':>8}{'tokens':>9}{'U(tok)':>8}{'U':>8}{'fallb':>7}{'exposed':>8} | vs {ref}: dSucc [95% CI]        dTokens [CI]            dU(tok) [CI]")
    for c in cfgs:
        rs = [cell[k][c] for k in common]; n = len(rs); f = lambda k: sum(r["metrics"].get(k, 0) for r in rs) / n
        row = f"{c:20}{f('success'):>8.3f}{f('total_tokens'):>9.0f}{sum(U(r['metrics'],0) for r in rs)/n:>8.3f}{sum(U(r['metrics']) for r in rs)/n:>8.3f}{f('fallbacks'):>7.2f}{f('n_exposed'):>8.1f} | "
        if c != ref and ref in cfgs:
            ds = [cell[k][c]["metrics"]["success"] - cell[k][ref]["metrics"]["success"] for k in common]
            dt = [cell[k][c]["metrics"].get("total_tokens", 0) - cell[k][ref]["metrics"].get("total_tokens", 0) for k in common]
            du = [U(cell[k][c]["metrics"], 0) - U(cell[k][ref]["metrics"], 0) for k in common]
            row += f"{sum(ds)/n:+.3f} [{boot(ds)[0]:+.3f},{boot(ds)[1]:+.3f}]  {sum(dt)/n:+8.0f} [{boot(dt)[0]:+.0f},{boot(dt)[1]:+.0f}]  {sum(du)/n:+.3f} [{boot(du)[0]:+.3f},{boot(du)[1]:+.3f}]"
        print(row)
    # fallback causes
    cause = collections.Counter()
    for k in common:
        for c in cfgs:
            for s in cell[k][c]["steps"]:
                if s.get("kind") == "fallback": cause[(c, s["cause"])] += 1
    print("\nfallback events:", dict(cause))
if __name__ == "__main__": main(sys.argv[1], sys.argv[2:])
