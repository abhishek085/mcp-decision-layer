"""S2 task templates: (world, params) -> Task(instruction, verifier, reference solver). Verifiers check final state + answer."""
from dataclasses import dataclass
from typing import Callable
from collections import Counter
import re
from worlds.world import World, REPOS, SERVICES, CUSTOMERS

@dataclass
class Task:
    id: str; family: str; instruction: str; params: dict
    verify: Callable          # (world, answer_text) -> bool
    solve: Callable           # (world) -> answer_text, applies side effects directly on world
    needed_tools: list
    factors: dict

def _nums(s): return [int(x) for x in re.findall(r"-?\d+", s.replace(",", ""))]

def reminder(w: World, n: int, repo="atlas", cond=False):
    """per-item reminder: fan-out over open bug issues; message each assignee."""
    items = [i for i in w.issues.values() if i["repo"] == repo and i["state"] == "open"][:n]
    n = len(items)
    expect = {(i["assignee"], i["id"]) for i in items}
    ins = f"For each of the first {n} open issues (any label) in repo '{repo}' (in the order the tracker lists them), send the assignee a chat message that contains the issue id. Reply 'done' when finished."
    def verify(w2, ans):
        got = {(m["to"], next((x for x in re.findall(r"[A-Z]{3}-\d{4}", m["text"])), None)) for m in w2.messages}
        return got == expect and len(w2.messages) == n
    def solve(w2):
        for u, iid in sorted(expect): w2.messages.append({"to": u, "text": f"Reminder: {iid}"})
        return "done"
    return Task(f"reminder-{repo}-{n}", "reminder", ins, dict(n=n, repo=repo), verify, solve, ["list_issues", "post_message"],
                dict(depth=2, fanout=n, size="med", adapt="fixed", servers=2))

def who_is_assignee(w, issue_id=None):
    iid = issue_id or sorted(w.issues)[7]
    u = w.users[w.issues[iid]["assignee"]]
    ins = f"What is the full name of the assignee of issue {iid}? Answer with the name only."
    return Task(f"assignee-{iid}", "lookup", ins, dict(issue=iid), lambda w2, a: u["name"].lower() in a.lower(),
                lambda w2: u["name"], ["get_issue", "lookup_user"], dict(depth=2, fanout=1, size="small", adapt="fixed", servers=2))

def chain_dm(w, issue_id=None):
    iid = issue_id or sorted(w.issues)[11]
    uid = w.issues[iid]["assignee"]
    ins = f"Find the assignee of issue {iid}, look up their name, and send them a chat message of the form 'Hi <full name>, please review {iid}'. Reply 'done'."
    def verify(w2, a):
        name = w2.users[uid]["name"]
        return len(w2.messages) == 1 and w2.messages[0]["to"] == uid and name in w2.messages[0]["text"] and iid in w2.messages[0]["text"]
    def solve(w2): w2.messages.append({"to": uid, "text": f"Hi {w2.users[uid]['name']}, please review {iid}"}); return "done"
    return Task(f"chain-{iid}", "chain_dm", ins, dict(issue=iid), verify, solve, ["get_issue", "lookup_user", "post_message"],
                dict(depth=3, fanout=1, size="small", adapt="fixed", servers=2))

def log_top_error_service(w):
    c = Counter(l["service"] for l in w.logs if l["level"] == "ERROR"); top = c.most_common(1)[0][0]
    ins = "Which service has the most ERROR-level log lines? Answer with the service name only."
    return Task("logtop", "log_agg", ins, {}, lambda w2, a: top in a.lower() and sum(s in a.lower() for s in SERVICES) == 1,
                lambda w2: top, ["aggregate_logs"], dict(depth=1, fanout=1, size="small", adapt="fixed", servers=1))

def log_count_scan(w, service="api"):
    """No server-side aggregate matches this: need to scan raw lines (large intermediate)."""
    n = sum(1 for l in w.logs if l["service"] == service and l["level"] == "WARN" and "cache" in l["msg"])
    ins = f"How many WARN-level log lines from the '{service}' service have a message containing the word 'cache'? Answer with the number only."
    return Task(f"logscan-{service}", "log_scan", ins, dict(service=service), lambda w2, a: _nums(a)[-1:] == [n] if _nums(a) else False,
                lambda w2: str(n), ["query_logs"], dict(depth=1, fanout=1, size="large", adapt="fixed", servers=1))

def billing_sum(w, customer="Acme"):
    tot = sum(i["amount"] - i["refunded"] * 0 for i in w.invoices.values() if i["customer"] == customer and i["status"] == "unpaid")
    ins = f"What is the total amount of all unpaid invoices for customer {customer}? Answer with the number only."
    return Task(f"billsum-{customer}", "bill_sum", ins, dict(customer=customer), lambda w2, a: bool(_nums(a)) and _nums(a)[-1] == tot,
                lambda w2: str(tot), ["list_invoices"], dict(depth=1, fanout=1, size="med", adapt="fixed", servers=1))

def refund_overdue(w, customer="Birch", threshold=1000):
    tgt = {i["id"]: i["amount"] for i in w.invoices.values() if i["customer"] == customer and i["status"] == "overdue" and i["amount"] > threshold}
    ins = f"Issue a full refund (refund amount equal to the invoice amount) for every overdue invoice of customer {customer} whose amount exceeds {threshold}. Reply 'done'."
    def verify(w2, a): return all(i["refunded"] == (tgt.get(i["id"], 0)) for i in w2.invoices.values())
    def solve(w2):
        for k, v in tgt.items(): w2.invoices[k]["refunded"] += v
        return "done"
    return Task(f"refund-{customer}", "refund_cond", ins, dict(customer=customer, n=len(tgt)), verify, solve, ["list_invoices", "issue_refund"],
                dict(depth=2, fanout=len(tgt), size="med", adapt="conditional", servers=1))

def find_codeword(w):
    ins = f"One issue has a comment containing the code '{w.codeword}'. Who (full name) is that issue's assignee? Answer with the name only."
    u = w.users[w.issues[w.codeword_issue]["assignee"]]["name"]
    return Task("codeword", "explore", ins, {}, lambda w2, a: u.lower() in a.lower(), lambda w2: u,
                ["search_comments", "get_issue", "lookup_user"], dict(depth=3, fanout=1, size="small", adapt="exploratory", servers=2))

def top_assignee_open_bugs(w, repo="beacon"):
    c = Counter(i["assignee"] for i in w.issues.values() if i["repo"] == repo and i["state"] == "open" and i["label"] == "bug")
    best = max(c.values()); tops = [w.users[u]["name"] for u, v in c.items() if v == best]
    ins = f"In repo '{repo}', which person is assigned the most open bug issues? Answer with the full name only (if tied, any tied person is fine)."
    return Task(f"topassign-{repo}", "join_agg", ins, dict(repo=repo), lambda w2, a: any(t.lower() in a.lower() for t in tops),
                lambda w2: tops[0], ["list_issues", "lookup_user"], dict(depth=2, fanout=1, size="large", adapt="fixed", servers=2))

def build_suite(w: World):
    t = [who_is_assignee(w), chain_dm(w), log_top_error_service(w), log_count_scan(w, "api"), log_count_scan(w, "worker"),
         billing_sum(w, "Acme"), billing_sum(w, "Fjord"), refund_overdue(w, "Birch"), refund_overdue(w, "Ember", 500),
         find_codeword(w), top_assignee_open_bugs(w, "beacon"), top_assignee_open_bugs(w, "cinder")]
    for n in (1, 5, 15, 30): t.append(reminder(w, n))
    t.append(reminder(w, 5, "beacon")); t.append(reminder(w, 15, "cinder"))
    return t
