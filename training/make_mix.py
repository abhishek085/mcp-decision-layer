"""Training mix = new MCP tool-need records + replay of existing spark-s1 training rows (protects agent-decision skills)."""
import json, random, sys
random.seed(0)
new = [l for l in open("training/data/mcp_router_train.jsonl")]
n_replay = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
src = "../Open-Spark-Jev/data/mixes/v7_13_train.jsonl"
rows = []
with open(src) as f:
    for i, l in enumerate(f):
        if len(l) < 6000: rows.append(l)       # keep it short (max_len 2048)
rep = random.sample(rows, min(n_replay, len(rows)))
mix = new + rep; random.shuffle(mix)
open("training/data/mcp_router_mix.jsonl", "w").writelines(mix)
print("new", len(new), "replay", len(rep), "total", len(mix))
