"""Training-world task generator for spark-s1-mcp-router.
Uses the same task templates as the eval suite but (a) a disjoint world (salt 'train', seeds >= 100), (b) randomised parameters, and
(c) EXCLUDES held-out template families and the tools of held-out servers (never seen in training, used to test generalisation)."""
import random, json, sys
sys.path.insert(0, ".")
from worlds.world import World, REPOS, SERVICES, CUSTOMERS
import tasks.templates as T
import tasks.templates2 as T2

HELDOUT_FAMILIES = {"chain_deep", "doc_append", "cal_cond", "ticket_triage", "cross3"}
HELDOUT_SERVERS = {"hr", "inventory", "support", "deployments"}
HELDOUT_TOOLS = {"get_person", "list_team", "get_team_lead", "list_skus", "stock_level", "list_orders", "restock", "list_tickets", "get_ticket",
                 "triage_ticket", "assign_ticket", "list_deployments", "get_deployment", "rollback_deployment"}

def sample_tasks(seed, rng):
    w = World(seed, "medium", "train"); out = []
    iss = sorted(w.issues)
    for _ in range(3): out.append(T.who_is_assignee(w, rng.choice(iss)))
    for _ in range(3): out.append(T.chain_dm(w, rng.choice(iss)))
    out.append(T.log_top_error_service(w))
    for s in rng.sample(SERVICES, 3): out.append(T.log_count_scan(w, s))
    for c in rng.sample(CUSTOMERS, 3): out.append(T.billing_sum(w, c))
    for c in rng.sample(CUSTOMERS, 2): out.append(T.refund_overdue(w, c, rng.choice([300, 500, 1000, 2000])))
    out.append(T.find_codeword(w))
    for r in rng.sample(REPOS, 2): out.append(T.top_assignee_open_bugs(w, r))
    for n in rng.sample([1, 2, 3, 5, 8, 12, 20, 30], 3): out.append(T.reminder(w, n, rng.choice(REPOS)))
    out.append(T2.crm_promote(w, rng.choice(["smb", "mid", "ent"]), rng.choice(["lead", "trial"]), rng.choice(["trial", "customer"])))
    out.append(T2.docs_codeword(w))
    out.append(T2.files_sum(w, rng.choice(["reports/q1", "reports/q2", "reports/q3", "reports/q4", "reports/"])))
    keep = []
    for t in out:
        if t.family in HELDOUT_FAMILIES or (set(t.needed_tools) & HELDOUT_TOOLS): continue
        w0 = World(seed, "medium", "train")
        if t.verify(w0, "zzz"): continue       # vacuous (no-op passes)
        w1 = World(seed, "medium", "train")
        try:
            if not t.verify(w1, t.solve(w1)): continue
        except Exception: continue
        keep.append(t)
    return keep

def build(n_seeds=40, seed0=100):
    rows = {}
    for s in range(seed0, seed0 + n_seeds):
        rng = random.Random(f"gen-{s}")
        for t in sample_tasks(s, rng):
            key = t.instruction
            if key not in rows: rows[key] = dict(task_id=t.id, family=t.family, instruction=t.instruction, gold=t.needed_tools, seed=s, factors=t.factors)
    return list(rows.values())

if __name__ == "__main__":
    rows = build(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
    import collections
    print(len(rows), "unique instructions;", dict(collections.Counter(r["family"] for r in rows)))
    with open(sys.argv[2] if len(sys.argv) > 2 else "training/data_train_tasks.jsonl", "w") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
