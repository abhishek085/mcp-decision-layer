import json, sys, collections
sys.path.insert(0, ".")
from bench.toolsel import metrics
rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
by = collections.defaultdict(list)
for r in rows: by[r["n_dist"]].append(r)
def agg(ms): return dict(complete=sum(m["complete"] for m in ms) / len(ms), frac=sum(m["frac"] for m in ms) / len(ms), n_sel=sum(m["n_sel"] for m in ms) / len(ms), extra=sum(m["extra"] for m in ms) / len(ms))
for nd, rs in sorted(by.items()):
    print(f"\n### catalog = {42 + nd} tools ({len(rs)} tasks)")
    print(f"{'method':32}{'complete-recall':>16}{'frac-recall':>12}{'n_sel':>7}{'extra':>7}{'ms/task':>9}")
    def line(name, sels, ms=None):
        a = agg([metrics(s, r["gold"], 0) for s, r in zip(sels, rs)])
        print(f"{name:32}{a['complete']:>16.3f}{a['frac']:>12.3f}{a['n_sel']:>7.1f}{a['extra']:>7.1f}{(ms or 0):>9.0f}")
    for th in (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3):
        if "c_per_tool" in rs[0]["methods"]:
            line(f"(c) per-tool bool th={th}", [[k for k, v in r["methods"]["c_per_tool"]["p"].items() if v >= th] for r in rs], sum(r["methods"]["c_per_tool"]["ms"] for r in rs) / len(rs))
    import worlds.distractors as D
    from bench.toolsel import catalog
    srv_of = {t["name"]: t["server"] for t in catalog(nd)}
    if "c_per_tool" in rs[0]["methods"]:
        for ths, th in ((0.1, 0.005), (0.1, 0.01), (0.1, 0.05)):
            line(f"(b) server>=0.1 then tool>={th}", [[k for k, v in r["methods"]["c_per_tool"]["p"].items() if v >= th and r["methods"]["b_server_probs"]["p"][srv_of[k]] >= 0.1] for r in rs],
                 sum(r["methods"]["b_server_probs"]["ms"] for r in rs) / len(rs))
    for th in (0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3):
        line(f"(a) embed30->spark th={th}", [[k for k, v in r["methods"]["a_embed30_spark"]["p"].items() if v >= th] for r in rs], sum(r["methods"]["a_embed30_spark"]["ms"] for r in rs) / len(rs))
    for k in (5, 8, 12, 20, 30):
        line(f"embed-only top-{k}", [r["methods"]["embed_rank"]["order"][:k] for r in rs])
    if "llm_router" in rs[0]["methods"]:
        line("prompted LLM router (Gemma)", [r["methods"]["llm_router"]["sel"] for r in rs], sum(r["methods"]["llm_router"]["ms"] for r in rs) / len(rs))
    print("(b) server-level probs recorded; two-stage analysis in report below")
