"""Clean serial latency + success + tokens per config, with component breakdown and paired bootstrap vs a reference config.
U = success - lt*tokens/1000 - ll*latency_s (primary lt=0.01, ll=0.002; also reports a latency-heavy ll=0.02)."""
import json, sys, statistics, random, collections
files = sys.argv[1:]; ref = "C"; random.seed(0)
R = [json.loads(l) for f in files for l in open(f)]
by = collections.defaultdict(dict)
for r in R: by[r["config"]][r["task_id"]] = r
cfgs = sorted(by, key=lambda c: (c != "A", c)); tasks = sorted(set.intersection(*[set(by[c]) for c in cfgs]))
def comp(r):
    st = r["steps"]; return dict(llm=sum(s.get("ms", 0) for s in st if s["kind"] == "llm") / 1000, sandbox=sum(s.get("ms", 0) for s in st if s["kind"] == "sandbox") / 1000,
                                 tool=sum(s.get("ms", 0) for s in st if s["kind"] == "tool") / 1000, router=r["metrics"].get("router_ms", 0) / 1000)
def U(m, ll, lt=0.01): return m["success"] - lt * m.get("total_tokens", 0) / 1000 - ll * m.get("latency_s", 0)
print(f"{len(tasks)} tasks common to {len(cfgs)} configs: {cfgs}\n")
print(f"{'config':18}{'succ':>6}{'tokens':>8}{'lat mean':>9}{'median':>8}{'p90':>7}{'| LLM':>7}{'router':>7}{'sandbox':>8}{'tool':>6}{'| U(tok+.002s)':>15}{'U(tok+.02s)':>12}")
for c in cfgs:
    rs = [by[c][t] for t in tasks]; lat = sorted(r["metrics"]["latency_s"] for r in rs); n = len(rs); cp = [comp(r) for r in rs]
    print(f"{c:18}{sum(r['metrics']['success'] for r in rs)/n:>6.2f}{sum(r['metrics']['total_tokens'] for r in rs)/n:>8.0f}{statistics.mean(lat):>9.1f}{lat[n//2]:>8.1f}{lat[int(n*.9)]:>7.1f}"
          f"{statistics.mean(x['llm'] for x in cp):>7.1f}{statistics.mean(x['router'] for x in cp):>7.1f}{statistics.mean(x['sandbox'] for x in cp):>8.1f}{statistics.mean(x['tool'] for x in cp):>6.2f}"
          f"{sum(U(r['metrics'],0.002) for r in rs)/n:>15.3f}{sum(U(r['metrics'],0.02) for r in rs)/n:>12.3f}")
print(f"\npaired differences vs {ref} (bootstrap 5,000, 95% CI):")
for c in cfgs:
    if c == ref: continue
    for name, f in (("latency s", lambda r: r["metrics"]["latency_s"]), ("success", lambda r: r["metrics"]["success"]), ("U(ll=.002)", lambda r: U(r["metrics"], .002)), ("U(ll=.02)", lambda r: U(r["metrics"], .02))):
        d = [f(by[c][t]) - f(by[ref][t]) for t in tasks]; bs = sorted(sum(random.choices(d, k=len(d))) / len(d) for _ in range(5000))
        print(f"  {c:18} {name:11} {sum(d)/len(d):+8.3f}  [{bs[125]:+.3f}, {bs[4875]:+.3f}]")
