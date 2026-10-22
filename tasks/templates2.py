"""Additional S2 families for the 8 extension servers (see templates.py for the Task contract)."""
import re
from collections import Counter
from worlds.world import World, SERVICES
from tasks.templates import Task, _nums

def deploy_rollback(w, service="api", env="prod"):
    tgt = {d["id"] for d in w.deploys.values() if d["service"] == service and d["env"] == env and d["status"] == "failed"}
    ins = f"Roll back every failed deployment of service '{service}' in the '{env}' environment. Reply 'done'."
    def solve(w2):
        for k in tgt: w2.deploys[k]["rolled_back"] = True
        return "done"
    return Task(f"rollback-{service}-{env}", "rollback", ins, dict(n=len(tgt)), lambda w2, a: {k for k, d in w2.deploys.items() if d["rolled_back"]} == tgt, solve,
                ["list_deployments", "rollback_deployment"], dict(depth=2, fanout=len(tgt), size="med", adapt="conditional", servers=1))

def restock_low(w, threshold=20, qty=50):
    exp = {k: v["stock"] + (qty if v["stock"] < threshold else 0) for k, v in w.skus.items()}
    ins = f"Restock by exactly {qty} units every SKU whose current stock is below {threshold}. Reply 'done'."
    def solve(w2):
        for k, v in exp.items(): w2.skus[k]["stock"] = v
        return "done"
    return Task(f"restock-{threshold}", "restock", ins, dict(n=sum(1 for k, v in w.skus.items() if exp[k] != v["stock"])), lambda w2, a: {k: v["stock"] for k, v in w2.skus.items()} == exp,
                solve, ["list_skus", "restock"], dict(depth=2, fanout=sum(1 for v in w.skus.values() if v["stock"] < threshold), size="med", adapt="conditional", servers=1))

def crm_promote(w, segment="ent", frm="trial", to="customer"):
    tgt = {a["id"] for a in w.accounts.values() if a["segment"] == segment and a["stage"] == frm}
    ins = f"Move every '{segment}' segment CRM account currently in stage '{frm}' to stage '{to}'. Reply 'done'."
    before = {k: a["stage"] for k, a in w.accounts.items()}
    def solve(w2):
        for k in tgt: w2.accounts[k]["stage"] = to
        return "done"
    return Task(f"crm-{segment}-{frm}", "crm_update", ins, dict(n=len(tgt)),
                lambda w2, a: all(x["stage"] == (to if k in tgt else before[k]) for k, x in w2.accounts.items()), solve, ["query_accounts", "update_account"],
                dict(depth=2, fanout=len(tgt), size="med", adapt="conditional", servers=1))

def ticket_email(w, priority="high"):
    tk = [t for t in w.tickets.values() if t["status"] == "open" and t["priority"] == priority]
    exp = {(w.users[t["assignee"]]["email"], t["id"]) for t in tk}
    ins = f"For each open support ticket with priority '{priority}', email its assignee (use the email address from the HR record) with subject 'Ticket <ticket id>' and any body. Reply 'done'."
    def verify(w2, a):
        got = {(e["to"], (re.findall(r"TKT-\d{4}", e["subject"]) or [None])[0]) for e in w2.emails_sent}
        return got == exp and len(w2.emails_sent) == len(exp)
    def solve(w2):
        for to, t in exp: w2.emails_sent.append(dict(to=to, subject=f"Ticket {t}", body="x"))
        return "done"
    return Task(f"ticketmail-{priority}", "ticket_email", ins, dict(n=len(exp)), verify, solve, ["list_tickets", "get_person", "send_email"],
                dict(depth=3, fanout=len(tk), size="med", adapt="fixed", servers=3))

def org_chain(w, depth):
    uid = f"u{depth:03d}"; n = 0; cur = uid
    while w.users[cur]["manager"]: cur = w.users[cur]["manager"]; n += 1
    ins = f"Starting from person {uid}, follow manager links upward until you reach the person with no manager. How many managers are in the chain, not counting {uid} themselves? Answer with the number only."
    return Task(f"orgchain-{depth}", "chain_deep", ins, dict(depth=depth), lambda w2, a: bool(_nums(a)) and _nums(a)[-1] == n, lambda w2: str(n), ["get_person"],
                dict(depth=n, fanout=1, size="small", adapt="exploratory", servers=1))

def docs_codeword(w):
    d = w.docs[w.codeword2_doc]; nm = w.users[d["author"]]["name"]
    ins = f"One knowledge-base document contains the reference code '{w.codeword2}'. Who is that document's author (full name)? Answer with the name only."
    return Task("doccode", "doc_search", ins, {}, lambda w2, a: nm.lower() in a.lower(), lambda w2: nm, ["search_docs", "read_doc", "lookup_user"],
                dict(depth=3, fanout=1, size="large", adapt="exploratory", servers=2))

def docs_append(w, tag="infra"):
    tgt = {d["id"] for d in w.docs.values() if tag in d["tags"]}; before = {k: d["body"] for k, d in w.docs.items()}
    ins = f"Append the text 'Reviewed' to every document tagged '{tag}'. Reply 'done'."
    def solve(w2):
        for k in tgt: w2.docs[k]["body"] += " Reviewed"
        return "done"
    return Task(f"docappend-{tag}", "doc_append", ins, dict(n=len(tgt)),
                lambda w2, a: all(d["body"] == before[k] + (" Reviewed" if k in tgt else "") for k, d in w2.docs.items()), solve, ["list_docs", "append_doc"],
                dict(depth=2, fanout=len(tgt), size="med", adapt="fixed", servers=1))

def files_sum(w, prefix):
    tot = sum(int(re.search(r"TOTAL: (\d+)", c).group(1)) for p, c in w.files.items() if p.startswith(prefix)); nf = sum(1 for p in w.files if p.startswith(prefix))
    ins = f"Each report file under '{prefix}' ends with a line 'TOTAL: <number>'. What is the sum of these TOTAL values over all files under '{prefix}'? Answer with the number only."
    return Task(f"filesum-{prefix.replace('/', '_')}", "file_sum", ins, dict(prefix=prefix), lambda w2, a: bool(_nums(a)) and _nums(a)[-1] == tot, lambda w2: str(tot),
                ["list_files", "read_file"], dict(depth=2, fanout=nf, size="large", adapt="fixed", servers=1))

def cal_conditional(w, team="data", day=5):
    mem = [u["id"] for u in w.users.values() if u["team"] == team]
    busy = {e["user"] for e in w.events if e["day"] == day}
    new = {u for u in mem if u not in busy}; before = len(w.events)
    ins = f"For every member of the '{team}' team, create a calendar event titled 'planning' on day {day} unless that person already has an event on day {day}. Reply 'done'."
    def verify(w2, a):
        added = w2.events[before:]
        return len(added) == len(new) and {e["user"] for e in added} == new and all(e["day"] == day and e["title"] == "planning" for e in added)
    def solve(w2):
        for u in sorted(new): w2.events.append(dict(user=u, day=day, title="planning"))
        return "done"
    return Task(f"cal-{team}-{day}", "cal_cond", ins, dict(n=len(new)), verify, solve, ["list_team", "list_events", "create_event"],
                dict(depth=3, fanout=len(mem), size="small", adapt="conditional", servers=2))

def ticket_escalate(w, customer="Acme"):
    tgt = {t["id"] for t in w.tickets.values() if t["customer"] == customer and t["status"] == "open" and t["priority"] == "low"}
    before = {k: t["priority"] for k, t in w.tickets.items()}
    ins = f"Set priority to 'high' on every open support ticket of customer {customer} that currently has priority 'low'. Reply 'done'."
    def solve(w2):
        for k in tgt: w2.tickets[k]["priority"] = "high"
        return "done"
    return Task(f"escalate-{customer}", "ticket_triage", ins, dict(n=len(tgt)),
                lambda w2, a: all(t["priority"] == ("high" if k in tgt else before[k]) for k, t in w2.tickets.items()), solve, ["list_tickets", "triage_ticket"],
                dict(depth=2, fanout=len(tgt), size="med", adapt="conditional", servers=1))

def invoice_lead_email(w, customer="Corvid", team="security"):
    inv = max((i for i in w.invoices.values() if i["customer"] == customer and i["status"] == "unpaid"), key=lambda i: (i["amount"], i["id"]), default=None)
    lead = w.users[w.team_lead[team]]["email"]
    ins = f"Find the unpaid invoice of customer {customer} with the largest amount. Then email the lead of the '{team}' team (their email address, from HR) with subject 'Invoice <invoice id>' and any body. Reply 'done'."
    def verify(w2, a): return inv is not None and len(w2.emails_sent) == 1 and w2.emails_sent[0]["to"] == lead and inv["id"] in w2.emails_sent[0]["subject"]
    def solve(w2): w2.emails_sent.append(dict(to=lead, subject=f"Invoice {inv['id']}", body="x")); return "done"
    return Task(f"invlead-{customer}", "cross3", ins, dict(), verify, solve, ["list_invoices", "get_team_lead", "get_person", "send_email"],
                dict(depth=4, fanout=1, size="med", adapt="fixed", servers=3))

def log_diag_rollback(w):
    c = Counter(l["service"] for l in w.logs if l["level"] == "ERROR"); top = max(c, key=lambda k: (c[k], k))
    fails = [d for d in w.deploys.values() if d["service"] == top and d["env"] == "prod" and d["status"] == "failed"]
    tgt = max(fails, key=lambda d: d["id"])["id"] if fails else None
    ins = "Find the service with the most ERROR-level log lines. Roll back that service's most recent failed deployment in 'prod' (the one with the highest deployment id). Reply 'done'."
    def solve(w2):
        if tgt: w2.deploys[tgt]["rolled_back"] = True
        return "done"
    return Task("logdiag", "explore2", ins, {}, lambda w2, a: tgt is not None and {k for k, d in w2.deploys.items() if d["rolled_back"]} == {tgt}, solve,
                ["aggregate_logs", "list_deployments", "rollback_deployment"], dict(depth=3, fanout=1, size="med", adapt="exploratory", servers=2))

def build_suite2(w: World):
    return [deploy_rollback(w, "api", "prod"), deploy_rollback(w, "worker", "staging"), restock_low(w, 20), restock_low(w, 40),
            crm_promote(w, "ent", "trial", "customer"), crm_promote(w, "smb", "lead", "trial"), ticket_email(w, "high"), ticket_email(w, "med"),
            org_chain(w, 6), org_chain(w, 12), org_chain(w, 20), docs_codeword(w), docs_append(w, "infra"), docs_append(w, "bug"),
            files_sum(w, "reports/q2"), files_sum(w, "reports/"), cal_conditional(w, "data", 5), cal_conditional(w, "platform", 3),
            ticket_escalate(w, "Acme"), ticket_escalate(w, "Fjord"), invoice_lead_email(w, "Corvid", "security"), invoice_lead_email(w, "Dunmore", "growth"), log_diag_rollback(w)]
