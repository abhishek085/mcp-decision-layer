"""Gateway: modes A (plain MCP), B (decision-model subset), C (code mode), D (subset + shape). One process, switches only."""
import asyncio, json, sys, time, os, textwrap, re, contextlib, math
import tiktoken
from openai import AsyncOpenAI
from mcp.shared.memory import create_connected_server_and_client_session as conn
from worlds.world import build_servers
from worlds.distractors import load_distractors, make_distractor_server

ENC = tiktoken.get_encoding("cl100k_base")
def ntok(x): return len(ENC.encode(x if isinstance(x, str) else json.dumps(x)))

SYS_A = "You are an agent that completes tasks by calling the provided tools. Call tools as needed (several per turn is fine). When the task is complete, reply with a brief final answer only."
SYS_C = """You are an agent that completes tasks by writing Python code against tools exposed through two meta tools:
- search(query): returns Python stubs (signature + docstring) for tools matching the query. Call it first to discover tools. Use a few keywords.
- execute(code): runs your Python script in a sandbox where every tool is ALREADY DEFINED as a plain function (positional or keyword args) returning parsed JSON (dict/list). Never redefine or stub these functions; just call them. Use print() to output ONLY the compact final result you need; large raw data must be processed inside the script, not printed.
Write one complete script that does the whole task (loops, filtering, paging, side effects). If it errors, fix and re-run (max 3 executions). When finished, reply with a brief final answer only (for side-effect tasks reply 'done')."""

class Hub:
    """Connects to all MCP servers (real protocol, in-memory transport) and exposes one flat tool namespace."""
    def __init__(self, world, n_dist=0): self.world = world; self.n_dist = n_dist; self.tools = {}; self.sess = {}; self.log = []
    async def __aenter__(self):
        self._stack = contextlib.AsyncExitStack()
        servers = {k: v._mcp_server for k, v in build_servers(self.world).items()}
        if self.n_dist: servers['distractors'] = make_distractor_server(load_distractors(self.n_dist))
        for name, srv in servers.items():
            c = await self._stack.enter_async_context(conn(srv))
            self.sess[name] = c
            for t in (await c.list_tools()).tools:
                self.tools[t.name] = dict(server=name, name=t.name, description=t.description or "", schema=t.inputSchema)
        return self
    async def __aexit__(self, *a): await self._stack.aclose()
    async def call(self, name, args):
        t0 = time.time()
        if name not in self.tools: return json.dumps({"error": f"unknown tool {name}"})
        try:
            r = await asyncio.wait_for(self.sess[self.tools[name]["server"]].call_tool(name, args), 30)
            txt = "".join(c.text for c in r.content if hasattr(c, "text"))
            if r.isError: txt = json.dumps({"error": txt[:300]})
        except Exception as e:
            txt = json.dumps({"error": str(e)[:300]})
        self.log.append(dict(kind="tool", name=name, result_tokens=ntok(txt), ms=int((time.time() - t0) * 1000), ok='"error"' not in txt[:20]))
        return txt

STOP = set("the a an of to for and or in on with by from is are be this that it as at all any each every get list find".split())
_IDF = {}
def search_rank(hub, names, q):
    key = tuple(names)
    if key not in _IDF:
        docs = {n: set(re.findall(r"[a-z0-9]+", (n.replace("_", " ") + " " + hub.tools[n]["description"]).lower())) for n in names}
        df = {}
        for d in docs.values():
            for w in d: df[w] = df.get(w, 0) + 1
        _IDF[key] = (docs, {w: math.log(1 + len(names) / c) for w, c in df.items()})
    docs, idf = _IDF[key]
    def sc(n):
        nm = set(re.findall(r"[a-z0-9]+", n.lower()))
        return -sum(idf.get(w, 0) * ((3 if w in nm else 0) + (1 if w in docs[n] else 0)) for w in q)
    return sorted(names, key=sc)

def oai_tool(t): return {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["schema"]}}

import keyword, builtins
def pyname(n):
    x = re.sub(r'[^0-9a-zA-Z_]', '_', n)
    if not x or x[0].isdigit() or keyword.iskeyword(x) or hasattr(builtins, x) or x.startswith('_'): x = 'tool_' + x.lstrip('_')
    return x

def stub(t):
    props = t["schema"].get("properties", {}); req = set(t["schema"].get("required", []))
    ty = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
    ps = [f"{k}: {ty.get(v.get('type'), 'object')}" + ("" if k in req else (" = " + repr(v.get("default", "")))) for k, v in props.items()]
    ps.sort(key=lambda s: "=" in s)
    return f'# already defined in the sandbox, just call it:\n{pyname(t["name"])}({", ".join(ps)}) -> dict | list   # {t["description"]}'

SANDBOX_PRELUDE = '''
import sys, json
def _rpc(name, **kw):
    sys.__stdout__.write("\\x00RPC" + json.dumps({"name": name, "args": kw}) + "\\n"); sys.__stdout__.flush()
    line = sys.stdin.readline()
    r = json.loads(line)
    try: return json.loads(r)
    except Exception: return r
'''
def sandbox_wrappers(tools):
    out = []
    for t in tools:
        order = list(t["schema"].get("properties", {}))
        out.append(f"def {pyname(t['name'])}(*a, **kw):\n    kw.update(dict(zip({order!r}, a)))\n    return _rpc({t['name']!r}, **kw)")
    return "\n".join(out)

async def run_sandbox(hub, code, names, timeout=60, max_calls=400):
    """Subprocess sandbox: no network use by design (only RPC to gateway). Rlimits applied. (Container isolation: TODO, logged.)"""
    script = SANDBOX_PRELUDE + sandbox_wrappers([hub.tools[n] for n in names]) + "\n" + code
    import resource
    def lim():
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30)); resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
    import tempfile
    tf = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, dir=os.environ.get("MDL_SANDBOX_TMP", None)); tf.write(script); tf.close()
    p = await asyncio.create_subprocess_exec(sys.executable, "-I", tf.name, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, preexec_fn=lim)
    out, calls, t0 = [], 0, time.time()
    async def loop():
        nonlocal calls
        while True:
            line = await p.stdout.readline()
            if not line: return
            s = line.decode(errors="replace")
            if s.startswith("\x00RPC"):
                calls += 1
                if calls > max_calls: p.kill(); out.append("ERROR: too many tool calls"); return
                req = json.loads(s[4:])
                res = await hub.call(req["name"], req["args"])
                p.stdin.write((json.dumps(res) + "\n").encode()); await p.stdin.drain()
            else: out.append(s)
    ok, err = True, ""
    try:
        await asyncio.wait_for(loop(), timeout)
        await asyncio.wait_for(p.wait(), 5)
    except asyncio.TimeoutError:
        p.kill(); ok = False; err = "ERROR: sandbox timeout"
    se = (await p.stderr.read()).decode(errors="replace")
    if p.returncode not in (0, None) and se: ok = False; err = se.strip().splitlines()[-1][:500] if se.strip() else "nonzero exit"
    try: os.unlink(tf.name)
    except OSError: pass
    txt = "".join(out)[:4000]
    return ok, (txt + ("\n" + err if err else "")) or "(no output)", calls

async def chat(client, model, msgs, tools=None, **kw):
    t0 = time.time()
    r = await client.chat.completions.create(model=model, messages=msgs, tools=tools or None, temperature=0, max_tokens=kw.get("max_tokens", 6000),
                                             extra_body=kw.get("extra_body"))
    return r, int((time.time() - t0) * 1000)

MORE_TOOL = {"type": "function", "function": {"name": "request_more_tools", "description": "Call this if you need a tool that is not in your current tool list. Returns additional tools that become callable.", "parameters": {"type": "object", "properties": {"need": {"type": "string", "description": "what capability you need"}}, "required": ["need"]}}}

async def json_phase(hub, task, client, model, exposed, m, steps, extra_body, ranking, allow_more, note="", ctx_limit=60000):
    """JSON tool-calling loop (mode A/B and D's JSON fallback). exposed: list of tool names (mutable)."""
    answer = ""
    msgs = [{"role": "system", "content": SYS_A + (" If a tool you need is missing, call request_more_tools." if allow_more else "")},
            {"role": "user", "content": task.instruction + (("\n\n" + note) if note else "")}]
    for turn in range(25):
        tools = [oai_tool(hub.tools[n]) for n in exposed] + ([MORE_TOOL] if allow_more else []); stok = ntok(tools)
        m["catalog_schema_tokens"] = stok
        if stok + 3000 > ctx_limit:
            m["ctx_overflow"] = 1; steps.append(dict(kind="error", cause="ctx_overflow", schema_tokens=stok)); return "", False
        r, ms = await chat(client, model, msgs, tools, extra_body=extra_body)
        m["llm_calls"] += 1; m["tokens_in"] += r.usage.prompt_tokens; m["tokens_out"] += r.usage.completion_tokens; m["schema_tokens"] += stok
        steps.append(dict(kind="llm", tokens_in=r.usage.prompt_tokens, tokens_out=r.usage.completion_tokens, ms=ms))
        msg = r.choices[0].message
        if not msg.tool_calls: return msg.content or "", True
        msgs.append({"role": "assistant", "content": msg.content or "", "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try: args = json.loads(tc.function.arguments or "{}")
            except Exception: args = {}
            if tc.function.name == "request_more_tools":
                m["more_tool_requests"] = m.get("more_tool_requests", 0) + 1
                rest = [n for n in (ranking or list(hub.tools)) if n not in exposed][:10]
                exposed.extend(rest); res = "Added tools: " + ", ".join(rest) if rest else "No more tools available."
                steps.append(dict(kind="fallback", cause="request_more_tools", added=rest))
            else:
                res = await hub.call(tc.function.name, args); m["tool_calls"] += 1
            m["result_tokens"] += ntok(res)
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": res})
    return "", False

async def code_phase(hub, task, client, model, names, m, steps, extra_body, max_exec=3):
    """Code mode loop (C and D's code branch). names: tools searchable/callable in the sandbox. Returns (answer, clean) where clean=False if the last execution failed or the limit was hit without a clean run."""
    meta = [{"type": "function", "function": {"name": "search", "description": "Search tool catalog; returns Python stubs.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
            {"type": "function", "function": {"name": "execute", "description": "Run a Python script in the sandbox with discovered tools as functions. Print only the final compact result.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}}]
    stok = ntok(meta); discovered = set(); last_ok = None; answer = ""; err = ""
    msgs = [{"role": "system", "content": SYS_C}, {"role": "user", "content": task.instruction}]
    for turn in range(10):
        r, ms = await chat(client, model, msgs, meta, extra_body=extra_body)
        m["llm_calls"] += 1; m["tokens_in"] += r.usage.prompt_tokens; m["tokens_out"] += r.usage.completion_tokens; m["schema_tokens"] += stok
        steps.append(dict(kind="llm", tokens_in=r.usage.prompt_tokens, tokens_out=r.usage.completion_tokens, ms=ms))
        msg = r.choices[0].message
        if not msg.tool_calls: answer = msg.content or ""; break
        msgs.append({"role": "assistant", "content": msg.content or "", "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try: args = json.loads(tc.function.arguments or "{}")
            except Exception: args = {}
            if tc.function.name == "search":
                q = set(re.findall(r"[a-z0-9]+", (args.get("query") or "").lower())) - STOP
                top = search_rank(hub, names, q)[:8] if q else []; discovered.update(top)
                res = "\n\n".join(stub(hub.tools[n]) for n in top) if q else "provide a query"
            elif tc.function.name == "execute":
                if m["exec_calls"] >= max_exec: res = "ERROR: execution limit reached; give your final answer."
                else:
                    m["exec_calls"] += 1; t1 = time.time()
                    ok, res, nc = await run_sandbox(hub, args.get("code", ""), [n for n in names if n in discovered]); last_ok = ok
                    if not ok: err = res[-200:]
                    steps.append(dict(kind="sandbox", ok=ok, ms=int((time.time() - t1) * 1000), tool_calls=nc, out=res[:400], code=args.get("code", "")[:1500]))
            else: res = "unknown tool"
            m["result_tokens"] += ntok(res)
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": res})
    clean = bool(answer) and last_ok is not False and "execution limit" not in answer.lower()
    return answer, clean, err

async def run_task(task, world, cfg, client, model, steps_out, extra_body=None, tool_subset=None, shape=None, n_dist=0, ctx_limit=60000, ranking=None, fallback=True, allow_more=None):
    """cfg: A | B | C | D. B = JSON with a subset (+request_more_tools). D = subset + shape ('json'|'code'); code failures fall back to JSON (plan 4.4).
    tool_subset: names exposed (None = all). ranking: retrieval order used by request_more_tools."""
    steps = steps_out; m = dict(schema_tokens=0, result_tokens=0, tokens_in=0, tokens_out=0, llm_calls=0, fallbacks=0, exec_calls=0, tool_calls=0)
    t_start = time.time(); answer = ""
    async with Hub(world, n_dist) as hub:
        names = list(hub.tools) if tool_subset is None else [n for n in hub.tools if n in tool_subset]
        if allow_more is None: allow_more = cfg in ("B", "D")
        if cfg in ("A", "B") or (cfg == "D" and shape == "json"):
            answer, _ = await json_phase(hub, task, client, model, list(names), m, steps, extra_body, ranking, allow_more and cfg != "A", ctx_limit=ctx_limit)
        elif cfg == "C" or (cfg == "D" and shape == "code"):
            answer, clean, err = await code_phase(hub, task, client, model, names, m, steps, extra_body)
            if cfg == "D" and fallback and not clean:
                m["fallbacks"] += 1; cause = "script_error" if err else "no_clean_answer"
                steps.append(dict(kind="fallback", cause=cause, err=err))
                note = f"NOTE: an earlier scripted attempt did not finish cleanly ({err or 'no clean result'}). Some actions may already have been applied; check current state before repeating any side effect."
                answer, _ = await json_phase(hub, task, client, model, list(names), m, steps, extra_body, ranking, True, note=note, ctx_limit=ctx_limit)
        else: raise ValueError(cfg)
        steps.extend(hub.log)
        m["tool_calls_backend"] = len(hub.log); m["backend_result_tokens"] = sum(s["result_tokens"] for s in hub.log)
    m["latency_s"] = round(time.time() - t_start, 2); m["total_tokens"] = m["tokens_in"] + m["tokens_out"]
    return answer, m
