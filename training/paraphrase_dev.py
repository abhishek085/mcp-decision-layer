"""TEST-side writer: Gemma rewrites DEV task instructions (different family from the train writer Nemotron); slot check + Qwen verification; used to test the router on wording it never saw."""
import json, sys, re, random, logging, concurrent.futures as cf
sys.path.insert(0, ".")
logging.disable(logging.INFO)
from openai import OpenAI
from worlds.world import World
from tasks.templates import build_suite
from training.paraphrase import slot_ok, STYLES
from training.verify_qwen import check_para
G = OpenAI(base_url="http://localhost:8002/v1", api_key="x", timeout=300)
tasks = {}
for s in (0, 1):
    for t in build_suite(World(s, "medium", "dev")): tasks[t.instruction] = t
def one(instr):
    rng = random.Random(instr); style = rng.choice(STYLES)
    p = (f"Rewrite the request below COMPLETELY IN YOUR OWN WORDS as {style}. Change the sentence structure and the vocabulary; do not just add a prefix, a label or a greeting to the original sentence. "
         f"Keep EXACTLY the same meaning, the same required actions and any required answer format. Every identifier, number, name and quoted value must be copied exactly as written. Do not add new requirements and do not explain. Output only the rewritten request.\n\nRequest: {instr}")
    r = G.chat.completions.create(model="gemma", messages=[{"role": "user", "content": p}], temperature=0.9, max_tokens=300)
    t = (r.choices[0].message.content or "").strip().strip('"')
    ok_slots = bool(t) and slot_ok(instr, t)
    return instr, dict(text=t, style=style, slots_ok=ok_slots, qwen_ok=check_para(instr, t) if ok_slots else False)
with cf.ThreadPoolExecutor(6) as ex: res = dict(ex.map(one, list(tasks)))
kept = {k: v["text"] for k, v in res.items() if v["slots_ok"] and v["qwen_ok"] and re.sub(r"\W+", " ", v["text"].lower()) != re.sub(r"\W+", " ", k.lower())}
json.dump(dict(all=res, kept=kept), open("traces/dev_paraphrases_gemma.json", "w"), indent=1)
print("dev instructions", len(res), "| slot ok", sum(v["slots_ok"] for v in res.values()), "| qwen ok", sum(v["qwen_ok"] for v in res.values()), "| kept (non-copy)", len(kept))
for k, v in list(kept.items())[:3]: print(" ORIG:", k[:110], "\n  ->", v[:170].replace("\n", " "))
