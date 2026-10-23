"""Clean, serial latency of the tool-selection step (no SUT running). Per task: embedding retrieval, then each router variant. Reports mean/median/p90 ms."""
import sys, time, json, statistics, re, logging
sys.path.insert(0, ".")
logging.disable(logging.INFO)
import httpx
from openai import OpenAI
from worlds.world import World
from tasks.templates import build_suite
from bench.toolsel import catalog
from gateway.router import embed_rank, short
from training.build_records import render_state, Q_PROMPT
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
tools = catalog(0); tasks = [t for s in (0, 1) for t in build_suite(World(s, "medium", "dev"))][:N]
def post(url, state, names):
    qs = [dict(id=n, type="boolean", instructions=Q_PROMPT.format(name=n)) for n in names]
    return httpx.post(url, json={"state": state, "questions": qs}, timeout=300).json()
def router_plain(url, state, names): post(url, state, names)
def router_warm(url, state, names):             # first question alone fills the prefix cache, the rest then reuse it
    post(url, state, names[:1]); post(url, state, names[1:])
qwen = OpenAI(base_url="http://localhost:8888/v1", api_key="x", timeout=300); gem = OpenAI(base_url="http://localhost:8002/v1", api_key="x", timeout=300)
def llm_router(client, model, text):
    lst = "\n".join(f"- {t['name']}: {short(t['description'], 90)}" for t in tools)
    client.chat.completions.create(model=model, temperature=0, max_tokens=120, extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        messages=[{"role": "user", "content": f"Task: {text}\n\nAvailable tools:\n{lst}\n\nList the tools needed to complete the task (include every tool that might be needed, e.g. for lookups). Reply with a JSON array of tool names only."}])
variants = {}
def timeit(name, f):
    t0 = time.perf_counter(); f(); variants.setdefault(name, []).append((time.perf_counter() - t0) * 1000)
embed_rank(tasks[0].instruction, tools)       # warm model/caches
for url in ("http://localhost:8401/v1/decide", "http://localhost:8400/v1/decide"): post(url, "warm", ["a"])
for t in tasks:
    text = t.instruction
    timeit("embedding retrieval only (CPU, top-30)", lambda: embed_rank(text, tools))
    rk = embed_rank(text, tools)
    for k in (30, 15):
        cand = [tools[i] for i in rk[:k]]; state = render_state(text, cand); names = [c["name"] for c in cand]
        timeit(f"retrieval + FINE-TUNED 4B router, plain, k={k}", lambda: (embed_rank(text, tools), router_plain("http://localhost:8401/v1/decide", state, names)))
        timeit(f"retrieval + FINE-TUNED 4B router, prefix-warm, k={k}", lambda: (embed_rank(text, tools), router_warm("http://localhost:8401/v1/decide", state, names)))
    cand = [tools[i] for i in rk[:30]]; state = render_state(text, cand); names = [c["name"] for c in cand]
    timeit("retrieval + zero-shot spark-s1 v8 (nvfp4), prefix-warm, k=30", lambda: (embed_rank(text, tools), router_warm("http://localhost:8400/v1/decide", state, names)))
    timeit("prompted LLM router: Qwen3.8-27B (all 42 tools in prompt)", lambda: llm_router(qwen, "Qwen3.8-27B", text))
    if len(sys.argv) > 2 and sys.argv[2] == "gemma": timeit("prompted LLM router: Gemma-4-26B", lambda: llm_router(gem, "gemma", text))
print(f"{'variant':72}{'mean ms':>9}{'median':>8}{'p90':>8}")
res = {}
for k, v in variants.items():
    v = sorted(v); res[k] = dict(mean=statistics.mean(v), median=v[len(v) // 2], p90=v[int(len(v) * .9)], n=len(v))
    print(f"{k:72}{res[k]['mean']:>9.0f}{res[k]['median']:>8.0f}{res[k]['p90']:>8.0f}")
json.dump(res, open("traces/router_latency.json", "w"), indent=1)
