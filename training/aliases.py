"""Alias augmentation: Nemotron writes 3 alternative (name, description) pairs for each TRAINABLE tool so the router cannot just memorise names.
Qwen later verifies that each alias keeps the tool's function."""
import json, re, sys
sys.path.insert(0, ".")
from openai import OpenAI
from bench.toolsel import catalog
from training.train_tasks import HELDOUT_TOOLS
C = OpenAI(base_url="http://localhost:8003/v1", api_key="x", timeout=300)
tools = [t for t in catalog(0) if t["name"] not in HELDOUT_TOOLS]
out = {}
for t in tools:
    p = (f"A software tool is named '{t['name']}' with description: \"{t['description']}\".\nWrite 3 DIFFERENT alternative definitions of the SAME tool as another vendor might document it. "
         "Each has a snake_case name that does not reuse the original name's words where possible and a one-sentence description (max 25 words) of the same function and the same filters/arguments. "
         "Reply with JSON only: [{\"name\": ..., \"description\": ...}, ...]")
    r = C.chat.completions.create(model="nemotron", messages=[{"role": "user", "content": p}], temperature=0.8, max_tokens=500, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    try:
        alts = json.loads(re.search(r"\[.*\]", r.choices[0].message.content, re.S).group(0))
        alts = [a for a in alts if re.fullmatch(r"[a-z][a-z0-9_]{3,40}", a.get("name", "")) and a.get("description")]
    except Exception: alts = []
    out[t["name"]] = dict(original=t["description"], aliases=alts[:3])
    print(t["name"], [a["name"] for a in out[t["name"]]["aliases"]], flush=True)
json.dump(out, open("training/data/aliases_raw.json", "w"), indent=1)
