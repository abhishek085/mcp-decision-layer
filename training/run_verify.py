import json, re, sys, collections, logging, concurrent.futures as cf
logging.disable(logging.INFO)
sys.path.insert(0, ".")
from training.verify_qwen import check_para, check_alias, audit_labels
from bench.toolsel import catalog
rows = [json.loads(l) for l in open(sys.argv[1])]
cat = {t["name"]: t["description"] for t in catalog(0)}
norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()
def prep(r):
    for p in r["paraphrases"]:
        t = p["text"]; p["copy"] = norm(t) == norm(r["instruction"]); p["scaffold"] = bool(re.search(r"\[[A-Za-z][^\]]{2,}\]", t)) or len(t) > 2.5 * len(r["instruction"]) + 80
        p["qwen_ok"] = None
jobs = []
for r in rows:
    prep(r)
    for p in r["paraphrases"]:
        if p["slots_ok"] and not p["copy"] and not p["scaffold"]: jobs.append((r, p))
print("paraphrase checks:", len(jobs), flush=True)
def run_p(j):
    r, p = j; p["qwen_ok"] = check_para(r["instruction"], p["text"])
def run_a(j):
    name, a = j; a["qwen_ok"] = check_alias(name, cat[name], a)
def run_l(r): r["label_audit"] = audit_labels(r["instruction"], r["gold"], cat)
al = json.load(open(sys.argv[2])); ajobs = [(n, a) for n, v in al.items() for a in v["aliases"]]
with cf.ThreadPoolExecutor(6) as ex:
    list(ex.map(run_p, jobs)); print("paraphrases verified", flush=True)
    list(ex.map(run_a, ajobs)); print("aliases verified", flush=True)
    list(ex.map(run_l, rows)); print("labels audited", flush=True)
for r in rows:
    for p in r["paraphrases"]:
        if p["qwen_ok"] is None: p["qwen_ok"] = False       # copies / scaffolds / slot failures are not used
        if p["copy"]: p["slots_ok"] = False
with open(sys.argv[3], "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
ao = {n: [{"name": a["name"], "description": a["description"]} for a in v["aliases"] if a.get("qwen_ok")] for n, v in al.items()}
json.dump(ao, open(sys.argv[4], "w"), indent=1)
np_ = sum(1 for r in rows for p in r["paraphrases"] if p["slots_ok"] and p["qwen_ok"])
print("kept paraphrases", np_, "of", sum(len(r["paraphrases"]) for r in rows), "| aliases kept", sum(len(v) for v in ao.values()), "of", len(ajobs))
aud = collections.Counter(str(r["label_audit"].get("all_needed")) for r in rows); print("label audit all_needed:", dict(aud))
bad = [(r["family"], r["gold"], r["label_audit"]) for r in rows if r["label_audit"].get("all_needed") is False]
for b in bad[:8]: print("  FLAG", b)
