import json, random, collections, sys
random.seed(0)
cap = int(sys.argv[1]); n_replay = int(sys.argv[2])
recs = [json.loads(l) for l in open("training/data/mcp_router_train.jsonl")]
by = collections.defaultdict(list)
for r in recs: by[r["meta"]["family"]].append(r)
keep = []
for f, rs in by.items(): random.shuffle(rs); keep += rs[:cap]
src = "../Open-Spark-Jev/data/mixes/v7_13_train.jsonl"
rows = [l for l in open(src) if len(l) < 6000]
rep = random.sample(rows, n_replay)
mix = [json.dumps(r) + "\n" for r in keep] + rep; random.shuffle(mix)
open("training/data/mcp_router_mix_small.jsonl", "w").writelines(mix)
print("new", len(keep), dict(collections.Counter(r["meta"]["family"] for r in keep)), "replay", len(rep), "total", len(mix), "yes-frac", sum(r["target"]["label"] == "yes" for r in keep) / len(keep))
