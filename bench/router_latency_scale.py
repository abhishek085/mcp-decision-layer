import sys, time, statistics, logging
sys.path.insert(0, "."); logging.disable(logging.INFO)
import httpx
from openai import OpenAI
from worlds.world import World
from tasks.templates import build_suite
from bench.toolsel import catalog
from gateway.router import embed_rank, short
from training.build_records import render_state, Q_PROMPT
ND = int(sys.argv[1]); N = int(sys.argv[2])
tools = catalog(ND); tasks = [t for t in build_suite(World(0, "medium", "dev"))][:N]
qwen = OpenAI(base_url="http://localhost:8888/v1", api_key="x", timeout=600)
def post(state, names):
    qs = [dict(id=n, type="boolean", instructions=Q_PROMPT.format(name=n)) for n in names]
    httpx.post("http://localhost:8401/v1/decide", json={"state": state, "questions": qs}, timeout=300)
embed_rank(tasks[0].instruction, tools); post("warm", ["a"])
res = {k: [] for k in ("retrieval", "4B router k=15 warm", "4B router k=30", "Qwen-27B prompted, all tools in prompt", "Qwen-27B prompted, top-60 retrieved")}
def T(k, f):
    t0 = time.perf_counter(); f(); res[k].append((time.perf_counter() - t0) * 1000)
def llm(cand, text):
    lst = "\n".join(f"- {t['name']}: {short(t['description'], 90)}" for t in cand)
    qwen.chat.completions.create(model="Qwen3.8-27B", temperature=0, max_tokens=120, extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        messages=[{"role": "user", "content": f"Task: {text}\n\nAvailable tools:\n{lst}\n\nList the tools needed. Reply with a JSON array of tool names only."}])
for t in tasks:
    x = t.instruction; T("retrieval", lambda: embed_rank(x, tools)); rk = embed_rank(x, tools)
    for k, name in ((15, "4B router k=15 warm"), (30, "4B router k=30")):
        cand = [tools[i] for i in rk[:k]]; st = render_state(x, cand); nm = [c["name"] for c in cand]
        if "warm" in name: T(name, lambda: (post(st, nm[:1]), post(st, nm[1:])))
        else: T(name, lambda: post(st, nm))
    T("Qwen-27B prompted, top-60 retrieved", lambda: llm([tools[i] for i in rk[:60]], x))
    if ND <= 158: T("Qwen-27B prompted, all tools in prompt", lambda: llm(tools, x))
print(f"catalog {42 + ND} tools, {len(tasks)} tasks (serial)")
for k, v in res.items():
    if v: v = sorted(v); print(f"  {k:44} mean {statistics.mean(v):7.0f} ms   median {v[len(v)//2]:7.0f}   p90 {v[int(len(v)*.9)]:7.0f}")
