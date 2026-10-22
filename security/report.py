import json, sys, collections
def load(f): return [json.loads(l) for l in open(f)]
def rate(rs, k): return sum(1 for r in rs if r["attack"] and r["attack"][k]) / max(len(rs), 1)
def table(files, title):
    R = [r for f in files for r in load(f) if r.get("attack") and r["attack"].get("vector")]
    print(f"\n## {title}  (n={len(R)})")
    print(f"{'config':14}{'n':>5}{'inj':>6}{'ASR':>7}{'task-ok':>9}{'blocks/run':>11}{'scr-err':>8}")
    for c in sorted({r["config"] for r in R}):
        rs = [r for r in R if r["config"] == c]; n = len(rs)
        print(f"{c:14}{n:>5}{rate(rs,'injected'):>6.2f}{rate(rs,'goal_executed'):>7.3f}{sum(r['metrics']['success'] for r in rs)/n:>9.3f}{sum(r['attack'].get('screen_blocks',0) for r in rs)/n:>11.2f}{sum(r['attack'].get('screen_errors',0) for r in rs):>8}")
    for key in ("vector", "goal", "style"):
        print(f" ASR by {key}:")
        for v in sorted({r["attack"][key] for r in R}):
            row = []
            for c in sorted({r["config"] for r in R}):
                rs = [r for r in R if r["attack"][key] == v and r["config"] == c]
                row.append(f"{c}={rate(rs,'goal_executed'):.3f}(n={len(rs)})")
            print(f"   {v:10}", "  ".join(row))
    print(" ASR by goal x config (injection executed / injected-only):")
    for c in sorted({r["config"] for r in R}):
        rs = [r for r in R if r["config"] == c and r["attack"]["injected"]]
        print(f"   {c:14} injected runs={len(rs)}  ASR|injected={rate(rs,'goal_executed'):.3f}")
if __name__ == "__main__":
    table(sys.argv[2:], sys.argv[1])
