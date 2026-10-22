"""Nemotron (TRAIN writer) rewrites task instructions; a deterministic slot check keeps only rewrites that preserve every id/number/name/quoted value."""
import json, re, sys, math, random, concurrent.futures as cf
from openai import OpenAI
C = OpenAI(base_url="http://localhost:8003/v1", api_key="x", timeout=300)
STYLES = ["a terse chat message", "a polite email request", "a ticket written by a busy manager", "a casual Slack message", "a formal operations request", "a step-by-step checklist item",
          "an urgent message from a non-technical colleague", "a precise technical instruction"]

def slots(text):
    s = set(m.lower() for m in re.findall(r"[A-Za-z]+-\d{3,4}|\b[a-z]{2}\d{5}\b|\b\d+(?:[.,]\d+)?\b|'([^']+)'", text) if m)
    s |= set(m.lower() for m in re.findall(r"[A-Z]{3}-\d{4}|\b[a-z]{2}\d{5}\b|\b\d+\b", text))
    s |= set(m.lower().strip() for m in re.findall(r"'([^']+)'", text))
    s |= set(w.lower() for w in re.findall(r"\b(?:Acme|Birch|Corvid|Dunmore|Ember|Fjord)\b", text))
    return {x for x in s if x}

def slot_ok(orig, para):
    low = para.lower()
    return all(sl in low for sl in slots(orig))

def one(args):
    row, k, seed = args
    rng = random.Random(f"{seed}-{row['instruction']}")
    out = []
    for style in rng.sample(STYLES, min(k, len(STYLES))):
        prompt = (f"Rewrite the following request as {style}. Keep EXACTLY the same meaning and the same required actions. Every identifier, number, name and quoted value "
                  f"must be copied exactly as written. Do not add new requirements and do not explain. Output only the rewritten request.\n\nRequest: {row['instruction']}")
        try:
            r = C.chat.completions.create(model="nemotron", messages=[{"role": "user", "content": prompt}], temperature=0.9, top_p=0.95, max_tokens=300,
                                          extra_body={"chat_template_kwargs": {"enable_thinking": False}})
            t = (r.choices[0].message.content or "").strip().strip('"')
        except Exception as e:
            continue
        out.append(dict(style=style, text=t, slots_ok=bool(t) and slot_ok(row["instruction"], t)))
    return dict(row, paraphrases=out)

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    rows = [json.loads(l) for l in open(src)]
    fam_n = {}
    for r in rows: fam_n[r["family"]] = fam_n.get(r["family"], 0) + 1
    jobs = [(r, min(8, max(3, math.ceil(150 / fam_n[r["family"]]))), 0) for r in rows]
    with cf.ThreadPoolExecutor(8) as ex, open(dst, "w") as f:
        for res in ex.map(one, jobs):
            f.write(json.dumps(res) + "\n"); f.flush()
    print("done", len(jobs))
