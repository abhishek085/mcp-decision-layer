"""Phase 5: tool-subset selection quality, offline (no SUT). Dev worlds only. Gold = task.needed_tools."""
import sys, json, time, re, asyncio, argparse, math
sys.path.insert(0, ".")
import httpx, numpy as np
from openai import OpenAI
from worlds.world import World, build_servers
from worlds.distractors import load_distractors
from tasks.templates import build_suite

SPARK = "http://localhost:8400/v1/decide"
def catalog(n_dist):
    tools = []
    for sname, srv in build_servers(World(0, "small", "dev")).items():
        for t in srv._tool_manager._tools.values(): tools.append(dict(name=t.name, description=t.description or "", server=sname, own=True))
    for r in load_distractors(n_dist): tools.append(dict(name=r["name"], description=r["description"], server=r["server"], own=False))
    return tools
def short(d, n=160): return re.sub(r"\s+", " ", d)[:n]

def spark_bool(state, items, maxq=250):
    """items: list of (id, question text) -> {id: P(true)}. Chunked."""
    out = {}; toks = 0; t0 = time.time()
    for i in range(0, len(items), maxq):
        qs = [dict(id=k, type="boolean", instructions=q) for k, q in items[i:i + maxq]]
        r = httpx.post(SPARK, json={"state": state, "questions": qs}, timeout=600).json()
        for k, d in r["decisions"].items(): out[k] = d["probabilities"]["true"]
        toks += r["usage"]["input_tokens"]
    return out, dict(ms=int((time.time() - t0) * 1000), tokens=toks)

def q_tool(t): return f"Does completing this task require calling the tool '{t['name']}' ({short(t['description'])})?"

_emb = None
def embed_rank(task, tools):
    global _emb
    from fastembed import TextEmbedding
    if _emb is None: _emb = TextEmbedding("BAAI/bge-small-en-v1.5")
    key = tuple(t["name"] for t in tools)
    if not hasattr(embed_rank, "cache"): embed_rank.cache = {}
    if key not in embed_rank.cache:
        embed_rank.cache[key] = np.array(list(_emb.embed([t["name"].replace("_", " ") + ". " + short(t["description"], 300) for t in tools])))
    qv = np.array(list(_emb.embed([task])))[0]
    sims = embed_rank.cache[key] @ qv
    return list(np.argsort(-sims))

def metrics(sel, gold, n_total):
    sel, gold = set(sel), set(gold); hit = len(sel & gold)
    return dict(complete=int(gold <= sel), frac=hit / len(gold), n_sel=len(sel), extra=len(sel - gold))

def run(n_dist, seeds, thetas, llm=True):
    tools = catalog(n_dist); names = [t["name"] for t in tools]; res = []
    gem = OpenAI(base_url="http://localhost:8002/v1", api_key="x", timeout=300)
    servers = {}
    for t in tools: servers.setdefault(t["server"], []).append(t)
    for seed in seeds:
        for task in build_suite(World(seed, "medium", "dev")):
            gold = task.needed_tools; row = dict(task=task.id, seed=seed, n_dist=n_dist, gold=gold, methods={})
            # M1 per-tool boolean (design c) - skip when too many tools
            if len(tools) <= 250:
                p, info = spark_bool(task.instruction, [(t["name"], q_tool(t)) for t in tools]); row["methods"]["c_per_tool"] = dict(p=p, **info)
            # M2 two-stage (design b)
            sp, i1 = spark_bool(task.instruction, [(s, f"Is any tool of the '{s}' server needed to complete this task? It offers: " + "; ".join(short(x["name"] + " - " + x["description"], 70) for x in v[:4])) for s, v in servers.items()])
            row["methods"]["b_server_probs"] = dict(p=sp, **i1)
            # M3 embedding rank
            rk = embed_rank(task.instruction, tools); row["methods"]["embed_rank"] = dict(order=[names[i] for i in rk[:60]])
            # M4 embed top-30 -> spark boolean (design a)
            cand = [tools[i] for i in rk[:30]]; p4, i4 = spark_bool(task.instruction, [(t["name"], q_tool(t)) for t in cand]); row["methods"]["a_embed30_spark"] = dict(p=p4, **i4)
            # M5 prompted LLM router (Gemma) on top-60 (or all if <=60)
            if llm:
                cand = tools if len(tools) <= 60 else [tools[i] for i in rk[:60]]
                lst = "\n".join(f"- {t['name']}: {short(t['description'], 90)}" for t in cand)
                t0 = time.time()
                r = gem.chat.completions.create(model="gemma", temperature=0, max_tokens=300, messages=[{"role": "user", "content": f"Task: {task.instruction}\n\nAvailable tools:\n{lst}\n\nList the tools needed to complete the task (include every tool that might be needed, e.g. for lookups). Reply with a JSON array of tool names only."}])
                txt = r.choices[0].message.content or ""
                try: sel = [x for x in json.loads(re.search(r"\[.*\]", txt, re.S).group(0)) if x in names]
                except Exception: sel = []
                row["methods"]["llm_router"] = dict(sel=sel, ms=int((time.time() - t0) * 1000), tokens=r.usage.prompt_tokens)
            res.append(row)
    return res

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--ndist", type=int, default=0); ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1]); ap.add_argument("--out", required=True)
    a = ap.parse_args(); rows = run(a.ndist, a.seeds, None)
    with open(a.out, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    print("rows", len(rows))
