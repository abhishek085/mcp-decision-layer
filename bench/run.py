import asyncio, json, sys, time, argparse, uuid, logging
logging.disable(logging.INFO)
sys.path.insert(0, ".")
from openai import AsyncOpenAI
from worlds.world import World
from tasks.templates import build_suite
from gateway.gw import run_task

CTX = {"qwen": 250000, "gemma": 65000, "nemotron": 65000}
SUT = {"qwen": ("http://localhost:8888/v1", "Qwen3.8-27B"), "gemma": ("http://localhost:8002/v1", "gemma"), "nemotron": ("http://localhost:8003/v1", "nemotron")}

async def one(sem, task_id, salt, seed, size, cfg, sut, split, out, extra, n_dist=0):
    async with sem:
        w = World(seed, size, salt); snap = w.state_hash()
        task = [t for t in build_suite(w) if t.id == task_id][0]
        base, model = SUT[sut]; client = AsyncOpenAI(base_url=base, api_key="x", timeout=600)
        steps = []; err = None; ans = ""; met = {}
        try: ans, met = await run_task(task, w, cfg, client, model, steps, extra_body=extra, n_dist=n_dist, ctx_limit=CTX[sut])
        except Exception as e: err = f"{type(e).__name__}: {str(e)[:300]}"
        ok = bool(not err and task.verify(w, ans))
        rec = dict(n_dist=n_dist, run_id=uuid.uuid4().hex[:8], task_id=task_id, family=task.family, factors=task.factors, split=split, world_seed=seed, size=size,
                   snapshot_hash=snap, config=cfg, sut=sut, temperature=0.0, steps=steps, final=dict(answer=ans[:500], state_hash=w.state_hash()),
                   metrics=dict(success=int(ok), **met), error=err)
        out.write(json.dumps(rec) + "\n"); out.flush()
        return rec

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", nargs="+", default=["A", "C"]); ap.add_argument("--sut", default="qwen"); ap.add_argument("--salt", default="dev")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0]); ap.add_argument("--size", default="medium"); ap.add_argument("--split", default="pilot")
    ap.add_argument("--tasks", nargs="*"); ap.add_argument("--conc", type=int, default=4); ap.add_argument("--out", required=True)
    ap.add_argument("--no-think", action="store_true"); ap.add_argument("--ndist", type=int, default=0)
    a = ap.parse_args()
    extra = {"chat_template_kwargs": {"enable_thinking": False}} if a.no_think else None
    sem = asyncio.Semaphore(a.conc); jobs = []
    with open(a.out, "a") as out:
        for seed in a.seeds:
            ids = [t.id for t in build_suite(World(seed, a.size, a.salt)) if not a.tasks or t.id in a.tasks]
            for cfg in a.cfg:
                for tid in ids: jobs.append(one(sem, tid, a.salt, seed, a.size, cfg, a.sut, a.split, out, extra, a.ndist))
        t0 = time.time(); res = await asyncio.gather(*jobs)
    from collections import defaultdict
    agg = defaultdict(list)
    for r in res: agg[r["config"]].append(r)
    for c, rs in sorted(agg.items()):
        n = len(rs); print(c, f"n={n} success={sum(r['metrics']['success'] for r in rs)/n:.2f} tokens={sum(r['metrics'].get('total_tokens',0) for r in rs)/n:.0f} lat={sum(r['metrics'].get('latency_s',0) for r in rs)/n:.1f}s errors={sum(1 for r in rs if r['error'])}")
    print("wall", round(time.time() - t0), "s")
asyncio.run(main())
