"""Eval of a tool-need router in the NEW format (state = task + candidate list; one yes/no question per candidate). Candidates = embedding top-K of the catalog.
Works for zero-shot spark-s1 and for fine-tuned routers served behind an open_spark_jev gateway. Dev worlds only. Gold = task.needed_tools."""
import sys, json, time, re, argparse, logging
sys.path.insert(0, ".")
logging.disable(logging.INFO)
import httpx
from worlds.world import World
from tasks.templates import build_suite
from bench.toolsel import catalog, metrics
from gateway.router import embed_rank, short
from training.build_records import render_state, Q_PROMPT
from training.train_tasks import HELDOUT_FAMILIES, HELDOUT_TOOLS

def ask_router(url, model, state, names, maxq=40):
    out = {}; ms = 0
    for i in range(0, len(names), maxq):
        qs = [dict(id=n, type="boolean", instructions=Q_PROMPT.format(name=n)) for n in names[i:i + maxq]]
        t0 = time.time(); r = httpx.post(url, json={"state": state, "questions": qs, **({"model": model} if model else {})}, timeout=900).json()
        ms += int((time.time() - t0) * 1000)
        for k, d in r["decisions"].items(): out[k] = d["probabilities"]["true"]
    return out, ms

def run(url, model, n_dist, seeds, out_path, k=30, texts=None):
    tools = catalog(n_dist); names = [t["name"] for t in tools]; rows = []
    for seed in seeds:
        for t in build_suite(World(seed, "medium", "dev")):
            text = (texts or {}).get(t.instruction, t.instruction)
            rk = embed_rank(text, tools); cand = [tools[i] for i in rk[:k]]
            state = render_state(text, cand)
            p, ms = ask_router(url, model, state, [c["name"] for c in cand])
            rows.append(dict(task=t.id, seed=seed, family=t.family, gold=t.needed_tools, n_dist=n_dist, probs=p, ms=ms, cand=[c["name"] for c in cand],
                             unseen_family=t.family in HELDOUT_FAMILIES, unseen_tools=bool(set(t.needed_tools) & HELDOUT_TOOLS)))
    with open(out_path, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    return rows

def report(rows, label):
    def agg(rs, th):
        ms = [metrics([n for n, v in r["probs"].items() if v >= th], r["gold"], 0) for r in rs]
        return sum(m["complete"] for m in ms) / len(ms), sum(m["frac"] for m in ms) / len(ms), sum(m["n_sel"] for m in ms) / len(ms), sum(m["extra"] for m in ms) / len(ms)
    groups = {"all": rows, "seen families & tools": [r for r in rows if not r["unseen_family"] and not r["unseen_tools"]], "unseen tools": [r for r in rows if r["unseen_tools"]], "unseen families": [r for r in rows if r["unseen_family"]]}
    print(f"\n### {label}  (catalog {42 + rows[0]['n_dist']} tools, candidates {len(rows[0]['cand'])})")
    for g, rs in groups.items():
        if not rs: continue
        print(f" [{g}] n={len(rs)}   threshold:  complete-recall / frac-recall / n_sel / extra")
        for th in (0.002, 0.01, 0.05, 0.1, 0.2, 0.3, 0.5):
            c, f, n, e = agg(rs, th); print(f"    th={th:<6} {c:6.3f} {f:6.3f} {n:6.1f} {e:6.1f}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://localhost:8400/v1/decide"); ap.add_argument("--model", default=None)
    ap.add_argument("--ndist", type=int, default=0); ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1]); ap.add_argument("--out", required=True); ap.add_argument("--label", default="router")
    a = ap.parse_args(); rows = run(a.url, a.model, a.ndist, a.seeds, a.out); report(rows, a.label)
