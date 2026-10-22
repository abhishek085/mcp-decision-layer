"""Negative-tool pool for training: real catalog tools that are NOT among the 2,000 eval distractors (same seeded shuffle, rows 2000..)."""
import json, re, random, sys
sys.path.insert(0, ".")
import pandas as pd
from worlds.distractors import SELECTION_SEED, CATALOG
from worlds.world import World, build_servers
d = pd.read_parquet("worlds/distractors_raw/tools.parquet")
reserved = set()
for s in build_servers(World(0, "small", "dev")).values(): reserved |= set(s._tool_manager._tools)
used = set(json.loads(l)["name"] for l in open(CATALOG))
rng = random.Random(SELECTION_SEED); idx = list(range(len(d))); rng.shuffle(idx)
seen = set(reserved); pool = []
for i in idx:
    r = d.iloc[i]; name = re.sub(r"[^A-Za-z0-9_-]", "_", str(r.tool_name))[:64]
    desc = str(r.tool_description if isinstance(r.tool_description, str) else "").strip()
    if not name or name in seen or len(desc) < 20: continue
    try: sch = json.loads(r.input_schema if isinstance(r.input_schema, str) else "null")
    except Exception: continue
    if not isinstance(sch, dict) or sch.get("type") != "object": continue
    seen.add(name)
    if name in used: continue            # eval distractor -> never used in training
    pool.append(dict(name=name, description=desc[:600], server=str(r.server_name)))
json.dump(pool, open("training/data/neg_pool.json", "w"))
print("pool", len(pool), "overlap with eval distractors:", len({p['name'] for p in pool} & used))
