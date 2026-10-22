import json, sys, collections, random
R = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
by = collections.defaultdict(list)
for r in R: by[r["config"]].append(r)
print(f"{'config':14}{'n':>4}{'succ':>6}{'mean s':>8}{'median':>8}{'p90':>7}{'tokens':>8}{'router ms':>10}{'llm s':>7}{'sandbox s':>10}{'tool s':>7}")
for c, rs in sorted(by.items()):
    lat = sorted(r["metrics"]["latency_s"] for r in rs); n = len(rs)
    llm = sum(s.get("ms", 0) for r in rs for s in r["steps"] if s["kind"] == "llm") / 1000 / n
    sb = sum(s.get("ms", 0) for r in rs for s in r["steps"] if s["kind"] == "sandbox") / 1000 / n
    tl = sum(s.get("ms", 0) for r in rs for s in r["steps"] if s["kind"] == "tool") / 1000 / n
    print(f"{c:14}{n:>4}{sum(r['metrics']['success'] for r in rs)/n:>6.2f}{sum(lat)/n:>8.1f}{lat[n//2]:>8.1f}{lat[int(n*.9)]:>7.1f}{sum(r['metrics']['total_tokens'] for r in rs)/n:>8.0f}{sum(r['metrics'].get('router_ms',0) for r in rs)/n:>10.0f}{llm:>7.1f}{sb:>10.1f}{tl:>7.1f}")
# paired bootstrap vs C
cell = collections.defaultdict(dict)
for r in R: cell[r["task_id"]][r["config"]] = r["metrics"]["latency_s"]
random.seed(0)
for c in sorted(by):
    if c == "C": continue
    xs = [v[c] - v["C"] for v in cell.values() if c in v and "C" in v]
    bs = sorted(sum(random.choices(xs, k=len(xs))) / len(xs) for _ in range(5000))
    print(f"latency {c} - C: {sum(xs)/len(xs):+.2f}s  95% CI [{bs[125]:+.2f}, {bs[4875]:+.2f}]  n={len(xs)}")
