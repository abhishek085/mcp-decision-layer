"""Gateway: modes A (plain MCP), B (decision-model subset), C (code mode), D (subset + shape). One process, switches only."""
import asyncio, json, sys, time, os, textwrap, re, contextlib
import tiktoken
from openai import AsyncOpenAI
from mcp.shared.memory import create_connected_server_and_client_session as conn
from worlds.world import build_servers

ENC = tiktoken.get_encoding("cl100k_base")
def ntok(x): return len(ENC.encode(x if isinstance(x, str) else json.dumps(x)))

SYS_A = "You are an agent that completes tasks by calling the provided tools. Call tools as needed (several per turn is fine). When the task is complete, reply with a brief final answer only."
SYS_C = """You are an agent that completes tasks by writing Python code against tools exposed through two meta tools:
- search(query): returns Python stubs (signature + docstring) for tools matching the query. Call it first to discover tools. Use a few keywords.
- execute(code): runs your Python script in a sandbox where every tool is ALREADY DEFINED as a plain function (positional or keyword args) returning parsed JSON (dict/list). Never redefine or stub these functions; just call them. Use print() to output ONLY the compact final result you need; large raw data must be processed inside the script, not printed.
Write one complete script that does the whole task (loops, filtering, paging, side effects). If it errors, fix and re-run (max 3 executions). When finished, reply with a brief final answer only (for side-effect tasks reply 'done')."""

class Hub:
    """Connects to all MCP servers (real protocol, in-memory transport) and exposes one flat tool namespace."""
    def __init__(self, world): self.world = world; self.tools = {}; self.sess = {}; self.log = []
    async def __aenter__(self):
        self._stack = contextlib.AsyncExitStack()
        for name, srv in build_servers(self.world).items():
            c = await self._stack.enter_async_context(conn(srv._mcp_server))
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

def oai_tool(t): return {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["schema"]}}

def stub(t):
    props = t["schema"].get("properties", {}); req = set(t["schema"].get("required", []))
    ty = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}
    ps = [f"{k}: {ty.get(v.get('type'), 'object')}" + ("" if k in req else (" = " + repr(v.get("default", "")))) for k, v in props.items()]
    ps.sort(key=lambda s: "=" in s)
    return f'# already defined in the sandbox, just call it:\n{t["name"]}({", ".join(ps)}) -> dict | list   # {t["description"]}'

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
        out.append(f"def {t['name']}(*a, **kw):\n    kw.update(dict(zip({order!r}, a)))\n    return _rpc({t['name']!r}, **kw)")
    return "\n".join(out)

async def run_sandbox(hub, code, names, timeout=60, max_calls=400):
    """Subprocess sandbox: no network use by design (only RPC to gateway). Rlimits applied. (Container isolation: TODO, logged.)"""
    script = SANDBOX_PRELUDE + sandbox_wrappers([hub.tools[n] for n in names]) + "\n" + code
    import resource
    def lim():
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30)); resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout))
    p = await asyncio.create_subprocess_exec(sys.executable, "-I", "-c", script, stdin=asyncio.subprocess.PIPE,
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
    txt = "".join(out)[:4000]
    return ok, (txt + ("\n" + err if err else "")) or "(no output)", calls

async def chat(client, model, msgs, tools=None, **kw):
    t0 = time.time()
    r = await client.chat.completions.create(model=model, messages=msgs, tools=tools or None, temperature=0, max_tokens=kw.get("max_tokens", 6000),
                                             extra_body=kw.get("extra_body"))
    return r, int((time.time() - t0) * 1000)

async def run_task(task, world, cfg, client, model, steps_out, extra_body=None, tool_subset=None, shape=None):
    """cfg: 'A' or 'C' (B/D reuse these with tool_subset / shape). Returns (answer, metrics)."""
    steps = steps_out; m = dict(schema_tokens=0, result_tokens=0, tokens_in=0, tokens_out=0, llm_calls=0, fallbacks=0, exec_calls=0, tool_calls=0)
    t_start = time.time()
    async with Hub(world) as hub:
        names = list(hub.tools) if tool_subset is None else [n for n in hub.tools if n in tool_subset]
        answer = ""
        if cfg in ("A", "B"):
            tools = [oai_tool(hub.tools[n]) for n in names]; stok = ntok(tools)
            msgs = [{"role": "system", "content": SYS_A}, {"role": "user", "content": task.instruction}]
            for turn in range(25):
                r, ms = await chat(client, model, msgs, tools, extra_body=extra_body)
                m["llm_calls"] += 1; m["tokens_in"] += r.usage.prompt_tokens; m["tokens_out"] += r.usage.completion_tokens; m["schema_tokens"] += stok
                steps.append(dict(kind="llm", tokens_in=r.usage.prompt_tokens, tokens_out=r.usage.completion_tokens, ms=ms))
                msg = r.choices[0].message
                if not msg.tool_calls: answer = msg.content or ""; break
                msgs.append({"role": "assistant", "content": msg.content or "", "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
                for tc in msg.tool_calls:
                    try: args = json.loads(tc.function.arguments or "{}")
                    except Exception: args = {}
                    res = await hub.call(tc.function.name, args)
                    m["result_tokens"] += ntok(res); m["tool_calls"] += 1
                    msgs.append({"role": "tool", "tool_call_id": tc.id, "content": res})
        else:  # C / D-code
            meta = [{"type": "function", "function": {"name": "search", "description": "Search tool catalog; returns Python stubs.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                    {"type": "function", "function": {"name": "execute", "description": "Run a Python script in the sandbox with discovered tools as functions. Print only the final compact result.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}}]
            stok = ntok(meta)
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
                        q = set(re.findall(r"\w+", (args.get("query") or "").lower()))
                        scored = sorted(names, key=lambda n: -sum(w in (n + " " + hub.tools[n]["description"]).lower() for w in q))
                        res = "\n\n".join(stub(hub.tools[n]) for n in scored[:8]) if q else "provide a query"
                    elif tc.function.name == "execute":
                        if m["exec_calls"] >= 3: res = "ERROR: execution limit reached; give your final answer."
                        else:
                            m["exec_calls"] += 1; t1 = time.time()
                            ok, res, nc = await run_sandbox(hub, args.get("code", ""), names)
                            steps.append(dict(kind="sandbox", ok=ok, ms=int((time.time() - t1) * 1000), tool_calls=nc, out=res[:400], code=args.get("code", "")[:1500]))
                    else: res = "unknown tool"
                    m["result_tokens"] += ntok(res)
                    msgs.append({"role": "tool", "tool_call_id": tc.id, "content": res})
        steps.extend(hub.log)
        m["tool_calls_backend"] = len(hub.log); m["backend_result_tokens"] = sum(s["result_tokens"] for s in hub.log)
    m["latency_s"] = round(time.time() - t_start, 2); m["total_tokens"] = m["tokens_in"] + m["tokens_out"]
    return answer, m
