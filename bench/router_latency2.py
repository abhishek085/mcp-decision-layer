"""Latency AND recall together for one router endpoint, serial, over the 79 template dev tasks (seeds 0,1) of the 42-tool catalog.
Variants: candidates k, description chars d in the state, plain (all questions in one request) vs warm (first question alone fills the prefix cache).
usage: router_latency2.py <decide_url> <label> [paraphrased]"""
import sys, time, json, statistics, logging
sys.path.insert(0, "."); logging.disable(logging.INFO)
import httpx
from worlds.world import World
from tasks.templates import build_suite
from bench.toolsel import catalog, metrics
from gateway.router import embed_rank, short
from training.build_records import Q_PROMPT
url, label = sys.argv[1], sys.argv[2]
para = json.load(open("traces/dev_paraphrases_gemma.json"))["kept"] if len(sys.argv) > 3 else None
tools = catalog(0)
tasks = [t for s in (0, 1) for t in build_suite(World(s, "medium", "dev")) if (para is None or t.instruction in para)]
def state_of(text, cand, d): return "Task: " + text + "\nCandidate tools:\n" + "\n".join(f"- {c['name']}: {short(c['description'], d)}" for c in cand)
def post(state, names):
    qs = [dict(id=n, type="boolean", instructions=Q_PROMPT.format(name=n)) for n in names]
    r = httpx.post(url, json={"state": state, "questions": qs}, timeout=600).json()
    return {k: v["probabilities"]["true"] for k, v in r["decisions"].items()}
post("warmup", ["a"])
embed_rank(tasks[0].instruction, tools)
variants = [(30, 90, "plain"), (30, 90, "warm"), (20, 90, "warm"), (15, 90, "warm"), (30, 60, "warm"), (20, 60, "warm"), (15, 60, "warm")]
out = {}
for k, d, mode in variants:
    ts, ms = [], []
    for t in tasks:
        text = para[t.instruction] if para else t.instruction
        t0 = time.perf_counter()
        rk = embed_rank(text, tools); cand = [tools[i] for i in rk[:k]]; names = [c["name"] for c in cand]; st = state_of(text, cand, d)
        if mode == "warm": post(st, names[:1]); p = post(st, names[1:]) | {}
        else: p = post(st, names)
        ts.append((time.perf_counter() - t0) * 1000)
        if mode == "warm":                                     # score of the first candidate comes from the warm request
            p |= post(st, names[:1])
        ms.append({th: metrics([n for n, v in p.items() if v >= th], t.needed_tools, 0) for th in (0.01, 0.05)})
    ts.sort(); rec = {th: (sum(m[th]["complete"] for m in ms) / len(ms), sum(m[th]["n_sel"] for m in ms) / len(ms)) for th in (0.01, 0.05)}
    out[f"k={k} d={d} {mode}"] = dict(mean=statistics.mean(ts), median=ts[len(ts)//2], p90=ts[int(len(ts)*.9)], rec01=rec[0.01], rec05=rec[0.05], n=len(ts))
    print(f"{label:30} k={k:2} d={d} {mode:5} latency mean {statistics.mean(ts):6.0f} median {ts[len(ts)//2]:6.0f} p90 {ts[int(len(ts)*.9)]:6.0f} ms | th=.01 recall {rec[0.01][0]:.3f} @ {rec[0.01][1]:.1f} tools | th=.05 recall {rec[0.05][0]:.3f} @ {rec[0.05][1]:.1f} tools (n={len(ts)})", flush=True)
json.dump(out, open(f"traces/router_latency2_{label.replace(' ', '_')}{'_para' if para else ''}.json", "w"), indent=1)
