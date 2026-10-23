"""Build spark-s1 'noul' training records for the MCP tool router.
STATE  = task text + candidate tool list (name + short description).  QUESTION = 'Is tool X needed...?'  TARGET = yes/no from code-derived gold.
Candidate lists imitate inference (embedding top-ranked tools over own+real tools, gold forced in); aliases rename own tools for some states."""
import json, random, re, sys, collections
sys.path.insert(0, ".")
import numpy as np
from bench.toolsel import catalog
from training.train_tasks import HELDOUT_TOOLS
from gateway.router import embed_rank, short
import gateway.router as R

Q_PROMPT = ("Is the tool '{name}' needed to complete the task? Count it as needed if the task directly requires it, or if its result "
            "(for example an id or a name) is needed as input for another step.")
def render_state(task, cands):
    return "Task: " + task + "\nCandidate tools:\n" + "\n".join(f"- {c['name']}: {short(c['description'], 90)}" for c in cands)

_EMBCACHE = {}
def emb_texts(texts):
    """Embed once per unique text (cached)."""
    from fastembed import TextEmbedding
    if "model" not in _EMBCACHE: _EMBCACHE["model"] = TextEmbedding("BAAI/bge-small-en-v1.5")
    new = [t for t in dict.fromkeys(texts) if t not in _EMBCACHE]
    if new:
        for t, v in zip(new, _EMBCACHE["model"].embed(new)): _EMBCACHE[t] = np.array(v)
    return np.stack([_EMBCACHE[t] for t in texts])
def tool_text(u): return u["name"].replace("_", " ") + ". " + short(u["description"], 300)

def build(paraphrased, aliases_ok, neg_pool, out_train, out_val, seed=0, states_per_text=3, n_pool=600, n_cand=22, nq=6, val_frac=0.05):
    rng = random.Random(seed)
    own = [t for t in catalog(0) if t["name"] not in HELDOUT_TOOLS]
    pool_all = neg_pool
    rows = [json.loads(l) for l in open(paraphrased)]
    # leakage filter (plan 6.2 step 5): drop training instructions identical to any dev/test-suite instruction (seeds 0-5)
    from worlds.world import World
    from tasks.templates import build_suite
    nz = lambda t: re.sub(r"\W+", " ", t.lower()).strip()
    devn = {nz(t.instruction) for salt in ("dev", "test") for sd in range(6) for t in build_suite(World(sd, "medium", salt))}
    before = len(rows); rows = [r for r in rows if nz(r["instruction"]) not in devn]
    print("leakage filter: dropped", before - len(rows), "of", before, "training instructions identical to dev/test suite instructions")
    stats = collections.Counter(); recs_tr, recs_va = [], []
    instr_ids = sorted({r["instruction"] for r in rows}); rng.shuffle(instr_ids)
    val_set = set(instr_ids[:max(1, int(len(instr_ids) * val_frac))])
    fam_ct = collections.Counter(r['family'] for r in rows for p in r['paraphrases'] if p.get('slots_ok') and p.get('qwen_ok', True))
    for r in rows:
        spt = states_per_text if fam_ct[r['family']] >= 30 else states_per_text * 3
        texts = [(r["instruction"], "template")] + [(p["text"], "nemotron") for p in r["paraphrases"] if p.get("slots_ok") and p.get("qwen_ok", True)]
        for text, src in texts:
            for si in range(spt):
                use_alias = rng.random() < 0.4
                mp = {}
                if use_alias:
                    for t in own:
                        al = aliases_ok.get(t["name"], [])
                        if al: a = rng.choice(al); mp[t["name"]] = dict(name=a["name"], description=a["description"])
                def view(t): return mp.get(t["name"], dict(name=t["name"], description=t["description"])) | dict(orig=t["name"], own=t.get("own", True))
                pool = [dict(name=p["name"], description=p["description"], own=False) for p in rng.sample(pool_all, n_pool)]
                universe = [view(t) for t in own] + [dict(p, orig=p["name"]) for p in pool]
                gold = set(r["gold"])
                qv = emb_texts([text])[0]
                sims = emb_texts([tool_text(u) for u in universe]) @ qv
                rk = list(np.argsort(-sims))
                chosen = [universe[i] for i in rk[:n_cand]]
                gset = [u for u in universe if u["orig"] in gold]
                for g in gset:
                    if g not in chosen:
                        # replace the lowest-ranked non-gold candidate
                        for k in range(len(chosen) - 1, -1, -1):
                            if chosen[k]["orig"] not in gold: chosen[k] = g; break
                rng.shuffle(chosen)
                state = render_state(text, chosen)
                gold_c = [c for c in chosen if c["orig"] in gold]; neg_c = [c for c in chosen if c["orig"] not in gold]
                hard = [c for c in sorted(neg_c, key=lambda c: next(i for i, u in enumerate(universe) if u is c or u["name"] == c["name"]))][:6]
                qs = gold_c[:3] + rng.sample(hard, min(len(hard), max(1, (nq - len(gold_c[:3])) // 2 + 1))) 
                rest = [c for c in neg_c if c not in qs]
                qs += rng.sample(rest, min(len(rest), max(0, nq - len(qs))))
                rng.shuffle(qs)
                for c in qs:
                    lab = "yes" if c["orig"] in gold else "no"
                    rec = {"id": f"mcp-router-{len(recs_tr)+len(recs_va):06d}", "domain": "mcp_tool_need", "source": "mdl:nemotron-writer" if src == "nemotron" else "mdl:template",
                           "state": {"content": state}, "question": {"type": "noul", "prompt": Q_PROMPT.format(name=c["name"])},
                           "target": {"label": lab, "dist": {"yes": 1.0 if lab == "yes" else 0.0, "no": 0.0 if lab == "yes" else 1.0}},
                           "meta": {"split": "val" if r["instruction"] in val_set else "train", "family": r["family"], "text_source": src, "alias": use_alias, "gold": r["gold"],
                                    "label_quality": "code_oracle", "n_cand": len(chosen)}}
                    (recs_va if r["instruction"] in val_set else recs_tr).append(rec)
                    stats[(lab, src)] += 1
    for path, recs in ((out_train, recs_tr), (out_val, recs_va)):
        with open(path, "w") as f:
            for x in recs: f.write(json.dumps(x) + "\n")
    print("train", len(recs_tr), "val", len(recs_va), dict(stats))

if __name__ == "__main__":
    pool = json.load(open("training/data/neg_pool.json"))
    ao = json.load(open("training/data/aliases_verified.json")) if len(sys.argv) < 2 else json.load(open(sys.argv[1]))
    build("training/data/train_paraphrased_verified.jsonl", ao, pool, "training/data/mcp_router_train.jsonl", "training/data/mcp_router_val.jsonl")
