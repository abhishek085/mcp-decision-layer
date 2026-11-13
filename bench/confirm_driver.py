"""Confirmatory run driver (PREREG 'Confirmatory protocol', tag confirmatory-freeze-v1).
Runs bench/run.py serially (concurrency 1) on the sealed test split (salt=test, seeds 0-2, medium) for each agent,
then the scale arm. Frozen flags: --stub-returns --no-think --fallback-policy full_code --theta 0.05, router = :8401.
Hang rule (PREREG): a run that exceeds the 900 s cap / hangs counts as a FAILURE (success 0, latency 900 s). If run.py stalls
(no new row for STALL s) it is killed, a synthetic failure row (flag synthetic_hang_failure) is written for the cell that was in
flight (serial order is deterministic), and run.py is resumed. No other re-runs are done here; infra errors are reviewed by hand."""
import json, os, subprocess, sys, time, urllib.request
sys.path.insert(0, ".")
from worlds.world import World
from tasks.templates import build_suite

PY = sys.executable; OUT = "traces/confirmatory"; STALL = 1100
CORE_CFGS = ["A", "B/mcprouter", "C", "D/mcprouter/code", "D/oracle/code"]
SCALE_TASKS = ['assignee-ATL-0008', 'chain-ATL-0012', 'logtop', 'billsum-Acme', 'refund-Birch', 'codeword', 'topassign-beacon', 'reminder-atlas-5', 'doccode', 'filesum-reports_q2']
def log(*a): print(time.strftime("%F %T"), *a, flush=True)

def up(port):
    try: return urllib.request.urlopen(f"http://localhost:{port}/v1/models", timeout=3).status == 200
    except Exception: return False
# Optional docker container names per agent (environment variables). If unset, the agent's server is assumed to be
# running already on its port and is left alone.
CONTAINERS = {"qwen": os.environ.get("QWEN_CONTAINER"), "gemma": os.environ.get("GEMMA_CONTAINER"), "nemotron": os.environ.get("NEMOTRON_CONTAINER")}
def ensure(sut, port, timeout=900):
    container = CONTAINERS.get(sut)
    if not up(port) and container:
        log("docker start", container); subprocess.run(["docker", "start", container], check=True, capture_output=True)
    t0 = time.time()
    while not up(port):
        if time.time() - t0 > timeout: raise SystemExit(f"{sut} server on port {port} not up")
        time.sleep(10)
    log(sut, "server up")
def release(sut):
    if CONTAINERS.get(sut): subprocess.run(["docker", "stop", CONTAINERS[sut]], capture_output=True); log("stopped", sut)

def order(seeds, cfgs, tasks):
    cells = []
    for seed in seeds:
        ids = [t.id for t in build_suite(World(seed, "medium", "test")) if not tasks or t.id in tasks]
        for c in cfgs:
            for tid in ids: cells.append((tid, seed, c))
    return cells

def rows(out):
    return [json.loads(l) for l in open(out)] if os.path.exists(out) else []

def stage(sut, cfgs, seeds, out, tasks=None, ndist=0, stub=True):
    cells = order(seeds, cfgs, tasks)
    while True:
        done = {(r["task_id"], r["world_seed"], r["config"]) for r in rows(out)}
        todo = [c for c in cells if c not in done]
        if not todo: log(sut, out, "complete", len(cells)); return
        cmd = [PY, "bench/run.py", "--cfg", *cfgs, "--sut", sut, "--salt", "test", "--seeds", *map(str, seeds), "--split", "confirmatory",
               "--conc", "1", "--out", out, "--no-think", *(["--stub-returns"] if stub else []), "--fallback-policy", "full_code", "--theta", "0.05", "--resume", "--ndist", str(ndist)]
        if tasks: cmd += ["--tasks", *tasks]
        log("launch", sut, out, "remaining", len(todo)); p = subprocess.Popen(cmd, stdout=open(out + ".stdout", "a"), stderr=subprocess.STDOUT)
        last = time.time(); n = len(rows(out))
        while p.poll() is None:
            time.sleep(15); m = len(rows(out))
            if m != n: n, last = m, time.time()
            if time.time() - last > STALL:
                log("STALL: killing run.py"); p.kill(); p.wait()
                done = {(r["task_id"], r["world_seed"], r["config"]) for r in rows(out)}
                nxt = [c for c in cells if c not in done][0]
                tid, seed, c = nxt
                row = dict(stub_returns=stub, n_dist=ndist, run_id="hang" + str(int(time.time()))[-4:], task_id=tid, family=None, factors=None, split="confirmatory", world_seed=seed, size="medium",
                           config=c, sut=sut, temperature=0.0, steps=[], final=dict(answer="", state_hash=None),
                           metrics=dict(success=0, total_tokens=0, latency_s=900.0), error="hang: exceeded 900 s cap (counted as failure per PREREG)", attack=None, synthetic_hang_failure=True)
                open(out, "a").write(json.dumps(row) + "\n"); log("wrote synthetic failure for", nxt); break
        else:
            if p.returncode != 0: log("run.py exit", p.returncode); time.sleep(30)

def main(which):
    os.makedirs(OUT, exist_ok=True)
    if "qwen" in which:
        ensure("qwen", 8888); stage("qwen", CORE_CFGS, [0, 1, 2], f"{OUT}/test_qwen_core.jsonl")
    if "scale" in which:
        ensure("qwen", 8888)
        for nd in (158, 1958): stage("qwen", ["A", "C", "D/mcprouter/code"], [0], f"{OUT}/test_qwen_scale_n{nd}.jsonl", tasks=SCALE_TASKS, ndist=nd)
    EXT_B = ["C", "D/mcprouter/code", "D/oracle/code"]
    if "ext-qwen" in which:
        ensure("qwen", 8888)
        stage("qwen", ["C"], [0, 1, 2], f"{OUT}/ext1_qwen_unhinted.jsonl", stub=False); stage("qwen", EXT_B, [3, 4, 5], f"{OUT}/ext2_qwen_s345.jsonl")
    for sut, port in (("gemma", 8002), ("nemotron", 8003)):
        if "ext-" + sut in which:
            ensure(sut, port); stage(sut, ["C"], [0, 1, 2], f"{OUT}/ext1_{sut}_unhinted.jsonl", stub=False); stage(sut, EXT_B, [3, 4, 5], f"{OUT}/ext2_{sut}_s345.jsonl")
            release(sut)
    for sut, port in (("gemma", 8002), ("nemotron", 8003)):
        if sut in which:
            ensure(sut, port); stage(sut, CORE_CFGS, [0, 1, 2], f"{OUT}/test_{sut}_core.jsonl")
            release(sut)
    log("ALL DONE", which)

if __name__ == "__main__": main(sys.argv[1:])
