"""Distractor catalog (plan 5.4): REAL tool definitions from a public catalog, non-executable (return 'unavailable').
Source: huggingface.co/datasets/automatelab/mcp-servers-tool-catalog (CC-BY-4.0), 9,922 tools. Selection seed recorded below."""
import json, os, random, re
from mcp.server.lowlevel import Server
import mcp.types as types

CATALOG = os.path.join(os.path.dirname(__file__), "distractors", "catalog_2000.jsonl")
SELECTION_SEED = 20251022

def build_catalog_file(raw="worlds/distractors_raw/tools.parquet", n=2000, reserved=()):
    import pandas as pd
    d = pd.read_parquet(raw); rng = random.Random(SELECTION_SEED); seen = set(reserved); rows = []
    idx = list(range(len(d))); rng.shuffle(idx)
    for i in idx:
        r = d.iloc[i]; name = re.sub(r"[^A-Za-z0-9_-]", "_", str(r.tool_name))[:64]
        desc = str(r.tool_description if isinstance(r.tool_description, str) else "").strip()
        if not name or name in seen or len(desc) < 20: continue
        try: sch = json.loads(r.input_schema if isinstance(r.input_schema, str) else "null")
        except Exception: continue
        if not isinstance(sch, dict) or sch.get("type") != "object": continue
        seen.add(name); rows.append(dict(name=name, description=desc[:1200], schema=sch, server=str(r.server_name), package=str(r.package)))
        if len(rows) >= n: break
    with open(CATALOG, "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
    return len(rows)

def load_distractors(n):
    with open(CATALOG) as f: rows = [json.loads(l) for l in f]
    return rows[:n]

def make_distractor_server(rows):
    srv = Server("distractors"); by = {r["name"]: r for r in rows}
    @srv.list_tools()
    async def _list(): return [types.Tool(name=r["name"], description=r["description"], inputSchema=r["schema"]) for r in rows]
    @srv.call_tool(validate_input=False)
    async def _call(name, arguments): return [types.TextContent(type="text", text='{"error":"unavailable: this tool is not available in this environment"}')]
    return srv
