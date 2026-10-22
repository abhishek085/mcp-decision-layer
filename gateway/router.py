"""Decision layer: tool-subset selection and invocation-shape decision. Only uses information known BEFORE the run (task text, catalog metadata)."""
import json, re, time
import httpx, numpy as np
from openai import OpenAI

SPARK = "http://localhost:8400/v1/decide"
_emb = None; _cache = {}
def short(d, n=160): return re.sub(r"\s+", " ", d)[:n]

def embed_rank(task, tools):
    """tools: list of dict(name, description). Returns indices best-first."""
    global _emb
    from fastembed import TextEmbedding
    if _emb is None: _emb = TextEmbedding("BAAI/bge-small-en-v1.5")
    key = tuple(t["name"] for t in tools)
    if key not in _cache: _cache[key] = np.array(list(_emb.embed([t["name"].replace("_", " ") + ". " + short(t["description"], 300) for t in tools])))
    qv = np.array(list(_emb.embed([task])))[0]
    return list(np.argsort(-(_cache[key] @ qv)))

def spark_bool(state, items, maxq=250):
    from gateway.thermal import wait_cool_sync; wait_cool_sync()
    out = {}; toks = 0
    for i in range(0, len(items), maxq):
        qs = [dict(id=k, type="boolean", instructions=q) for k, q in items[i:i + maxq]]
        r = httpx.post(SPARK, json={"state": state, "questions": qs}, timeout=600).json()
        for k, d in r["decisions"].items(): out[k] = d["probabilities"]["true"]
        toks += r["usage"]["input_tokens"]
    return out, toks

def q_tool(t): return f"Does completing this task require calling the tool '{t['name']}' ({short(t['description'])})?"

def select_tools(kind, task_text, tools, theta=0.002, llm_client=None, llm_model="gemma", gold=None, k_embed=30, llm_extra=None):
    """Returns (names, info). kinds: spark_a | llm | embed12 | oracle | all."""
    t0 = time.time(); names = [t["name"] for t in tools]; info = dict(kind=kind, tokens=0)
    if kind == "all": sel = names
    elif kind == "oracle": sel = [n for n in names if n in gold]
    elif kind.startswith("embed"):
        k = int(kind[5:]); rk = embed_rank(task_text, tools); sel = [names[i] for i in rk[:k]]
    elif kind == "spark_a":
        rk = embed_rank(task_text, tools); cand = [tools[i] for i in rk[:k_embed]]
        p, toks = spark_bool(task_text, [(t["name"], q_tool(t)) for t in cand]); info["tokens"] = toks
        sel = [n for n, v in p.items() if v >= theta]; info["probs"] = {n: round(v, 4) for n, v in p.items()}
    elif kind == "llm":
        rk = embed_rank(task_text, tools) if len(tools) > 60 else None
        cand = tools if rk is None else [tools[i] for i in rk[:60]]
        lst = "\n".join(f"- {t['name']}: {short(t['description'], 90)}" for t in cand)
        r = llm_client.chat.completions.create(model=llm_model, temperature=0, max_tokens=300, extra_body=llm_extra, messages=[{"role": "user", "content": f"Task: {task_text}\n\nAvailable tools:\n{lst}\n\nList the tools needed to complete the task (include every tool that might be needed, e.g. for lookups). Reply with a JSON array of tool names only."}])
        info["tokens"] = r.usage.prompt_tokens + r.usage.completion_tokens
        try: sel = [x for x in json.loads(re.search(r"\[.*\]", r.choices[0].message.content or "", re.S).group(0)) if x in names]
        except Exception: sel = []
    else: raise ValueError(kind)
    info["ms"] = int((time.time() - t0) * 1000); info["n_sel"] = len(sel)
    return sel, info

# ---- shape decision -------------------------------------------------------------------------------------------------
LARGE_TOOLS = {"query_logs", "read_file", "read_doc", "list_issues", "list_invoices", "list_tickets", "list_orders", "list_skus", "list_deployments", "query_accounts", "list_docs"}
def shape_features(task_text, subset):
    nums = [int(x) for x in re.findall(r"\b(\d+)\b", task_text)]
    return dict(quant=bool(re.search(r"\b(every|each|all|sum|total|count|how many|most)\b", task_text.lower())),
                maxnum=max(nums) if nums else 0, large=len(LARGE_TOOLS & set(subset)), n_tools=len(subset),
                chain=len(re.findall(r"\b(then|and then|follow|until|starting from)\b", task_text.lower())))

def shape_rule(task_text, subset, p):
    """Rule-based shape selector (plan 4.3): code if likely large/ many items or many planned calls. p = thresholds tuned on dev."""
    f = shape_features(task_text, subset)
    code = (f["quant"] and f["large"] >= p["min_large"]) or f["maxnum"] >= p["fanout"] or f["chain"] >= p["chain"]
    return ("code" if code else "json"), 1.0, f

def shape_spark(task_text, subset_desc):
    t0 = time.time()
    r = httpx.post(SPARK, json={"state": f"Task: {task_text}\nTools available: {subset_desc}", "questions": [{"id": "shape", "type": "choice",
        "instructions": "Which invocation shape fits this task better?", "options": [
        {"id": "json", "definition": "make individual tool calls one at a time and read each result; best for short lookups and few steps"},
        {"id": "code", "definition": "write one script that loops over many items, pages through large results, or aggregates data; best for fan-out and large data"}]}]}, timeout=120).json()
    d = r["decisions"]["shape"]
    return d["selected"], d["confidence"], dict(p_code=d["probabilities"]["code"], ms=int((time.time() - t0) * 1000))
