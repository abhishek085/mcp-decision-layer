"""Seeded mock world + 4 real MCP servers (issues, chat, logs, billing).
Structure and ground truth come from code. Free text is template-generated in this slice (LLM writer pass: TODO, see EXPERIMENT_LOG)."""
import hashlib, json, random, copy
from mcp.server.fastmcp import FastMCP

FIRST = "Ava Ben Cara Dev Elif Finn Gus Hana Ivan Jo Kira Leo Mia Noor Omar Pia Quin Raj Sana Tom Uma Vik Wen Xia Yuri Zane".split()
LAST = "Almeida Brandt Chen Dubois Evans Farah Gomez Haas Iyer Jensen Kapoor Lopez Mori Nagy Okafor Petrov Rossi Sato Tran Ueda".split()
REPOS = ["atlas", "beacon", "cinder"]
LABELS = ["bug", "feature", "docs", "infra"]
SERVICES = ["api", "auth", "billing", "search", "worker"]
CUSTOMERS = ["Acme", "Birch", "Corvid", "Dunmore", "Ember", "Fjord"]
WORDS = "latency cache retry timeout schema migration queue token index shard rollout flag lease quota backoff payload header cursor".split()

class World:
    def __init__(self, seed=0, size="medium", salt="train"):
        self.seed, self.size, self.salt = seed, size, salt
        rng = random.Random(f"{salt}-{seed}")
        n_issue = {"small": 20, "medium": 60, "large": 120}[size]       # rows per repo
        text_len = {"small": 12, "medium": 80, "large": 220}[size]     # words per description
        n_log = {"small": 200, "medium": 1500, "large": 6000}[size]
        n_inv = {"small": 30, "medium": 90, "large": 240}[size]
        names = set()
        while len(names) < 30: names.add(f"{rng.choice(FIRST)} {rng.choice(LAST)}")
        self.users = {f"u{i:03d}": {"id": f"u{i:03d}", "name": n} for i, n in enumerate(sorted(names))}
        uids = list(self.users)
        self.issues = {}
        k = 0
        for repo in REPOS:
            for _ in range(n_issue):
                k += 1
                iid = f"{repo[:3].upper()}-{k:04d}"
                self.issues[iid] = dict(id=iid, repo=repo, title=" ".join(rng.sample(WORDS, 3)),
                    state=rng.choices(["open", "closed"], [0.6, 0.4])[0], label=rng.choice(LABELS),
                    assignee=rng.choice(uids), description=" ".join(rng.choice(WORDS) for _ in range(text_len)), comments=[])
        self.messages = []   # side-effect log
        self.logs = []
        for i in range(n_log):
            self.logs.append(dict(ts=1_700_000_000 + i * 7, service=rng.choice(SERVICES),
                level=rng.choices(["INFO", "WARN", "ERROR"], [0.8, 0.12, 0.08])[0], msg=" ".join(rng.sample(WORDS, 4)) + f" id={rng.randrange(10**6)}"))
        self.invoices = {}
        for i in range(n_inv):
            iid = f"INV-{i:04d}"
            self.invoices[iid] = dict(id=iid, customer=rng.choice(CUSTOMERS), amount=rng.randrange(50, 5000),
                status=rng.choice(["paid", "unpaid", "overdue"]), refunded=0)
        # plant a codeword in one comment for exploratory tasks
        self.codeword = f"zx{rng.randrange(10**5):05d}"
        target = rng.choice(list(self.issues))
        self.issues[target]["comments"].append(f"note: ref {self.codeword}")
        self.codeword_issue = target

        # ---- extension (separate RNG stream so original seeds are unchanged) ----
        r2 = random.Random(f"{salt}-{seed}-ext")
        scale = {"small": 0.5, "medium": 1, "large": 2}[size]
        TEAMS = ["platform", "data", "growth", "security", "support"]
        for i, u in enumerate(self.users.values()):
            u["email"] = u["name"].lower().replace(" ", ".") + "@corp.example"
            u["team"] = TEAMS[i % 5]
            u["manager"] = (f"u{i-1:03d}" if i < 22 else f"u{r2.randrange(0, i):03d}") if i > 0 else None
        self.team_lead = {t: next(u["id"] for u in self.users.values() if u["team"] == t) for t in TEAMS}
        self.docs = {}
        for i in range(int(40 * scale)):
            did = f"DOC-{i:03d}"
            self.docs[did] = dict(id=did, title=" ".join(r2.sample(WORDS, 3)), author=r2.choice(uids),
                body=" ".join(r2.choice(WORDS) for _ in range(text_len * 3)), tags=[r2.choice(LABELS)])
        self.codeword2 = f"qk{r2.randrange(10**5):05d}"
        self.codeword2_doc = r2.choice(list(self.docs))
        self.docs[self.codeword2_doc]["body"] += f" appendix ref {self.codeword2}"
        self.events = [dict(user=u, day=r2.randrange(1, 11), title=r2.choice(["sync", "review", "1:1", "planning"])) for u in uids for _ in range(r2.randrange(1, 4))]
        self.emails_inbox = [dict(to=u, subject=" ".join(r2.sample(WORDS, 3)), body=" ".join(r2.choice(WORDS) for _ in range(text_len))) for u in uids for _ in range(r2.randrange(2, 6))]
        self.emails_sent = []
        self.accounts = {}
        for i in range(int(40 * scale)):
            aid = f"ACC-{i:03d}"
            self.accounts[aid] = dict(id=aid, name=f"{r2.choice(CUSTOMERS)} {r2.choice(WORDS).title()} {i}", segment=r2.choice(["smb", "mid", "ent"]),
                stage=r2.choice(["lead", "trial", "customer", "churned"]), owner=r2.choice(uids))
        self.files = {}
        for i in range(int(30 * scale)):
            pth = f"reports/{r2.choice(['q1','q2','q3','q4'])}/r{i:03d}.txt"
            val = r2.randrange(10, 999)
            self.files[pth] = f"Report {i}. " + " ".join(r2.choice(WORDS) for _ in range(text_len)) + f"\nTOTAL: {val}\n"
        self.deploys = {}
        for i in range(int(80 * scale)):
            did = f"DEP-{i:04d}"
            self.deploys[did] = dict(id=did, service=r2.choice(SERVICES), env=r2.choice(["prod", "staging"]), status=r2.choices(["success", "failed"], [0.75, 0.25])[0], version=f"1.{r2.randrange(30)}", rolled_back=False)
        self.skus = {f"SKU-{i:03d}": dict(sku=f"SKU-{i:03d}", name=r2.choice(WORDS) + f"-{i}", stock=r2.randrange(0, 200)) for i in range(int(60 * scale))}
        self.orders = {f"ORD-{i:04d}": dict(id=f"ORD-{i:04d}", sku=r2.choice(list(self.skus)), qty=r2.randrange(1, 20), status=r2.choice(["new", "shipped", "cancelled"])) for i in range(int(100 * scale))}
        self.tickets = {}
        for i in range(int(80 * scale)):
            tid = f"TKT-{i:04d}"
            self.tickets[tid] = dict(id=tid, subject=" ".join(r2.sample(WORDS, 3)), priority=r2.choice(["low", "med", "high"]), status=r2.choice(["open", "pending", "closed"]),
                assignee=r2.choice(uids), customer=r2.choice(CUSTOMERS))
        self._snap = self.state_hash()

    def _state(self):
        return dict(issues=self.issues, messages=self.messages, invoices=self.invoices, docs=self.docs, events=self.events, emails_sent=self.emails_sent, accounts=self.accounts, files=self.files, deploys=self.deploys, skus=self.skus, orders=self.orders, tickets=self.tickets)
    def state_hash(self):
        return hashlib.sha256(json.dumps(self._state(), sort_keys=True).encode()).hexdigest()[:16]

def J(x): return json.dumps(x, separators=(",", ":"))

def build_servers(w: World):
    s = {}
    iss = FastMCP("issues")
    @iss.tool()
    def list_issues(repo: str, state: str = "", label: str = "", limit: int = 50, offset: int = 0) -> str:
        """List issues in a repo (atlas|beacon|cinder), optionally filtered by state (open|closed) and label (bug|feature|docs|infra). Paged; returns id,title,state,label,assignee,description."""
        rows = [i for i in w.issues.values() if i["repo"] == repo and (not state or i["state"] == state) and (not label or i["label"] == label)]
        return J({"total": len(rows), "items": [{k: v for k, v in r.items() if k != "comments"} for r in rows[offset:offset + min(limit, 100)]]})
    @iss.tool()
    def get_issue(issue_id: str) -> str:
        """Get one issue by id, including its comments."""
        return J(w.issues.get(issue_id, {"error": "not found"}))
    @iss.tool()
    def update_issue(issue_id: str, state: str = "", assignee: str = "") -> str:
        """Update an issue's state (open|closed) and/or assignee (user id)."""
        i = w.issues.get(issue_id)
        if not i: return J({"error": "not found"})
        if state: i["state"] = state
        if assignee: i["assignee"] = assignee
        return J({"ok": True})
    @iss.tool()
    def add_comment(issue_id: str, text: str) -> str:
        """Add a comment to an issue."""
        i = w.issues.get(issue_id)
        if not i: return J({"error": "not found"})
        i["comments"].append(text); return J({"ok": True})
    @iss.tool()
    def search_comments(query: str) -> str:
        """Search issue comments for a substring; returns matching issue ids."""
        return J([i["id"] for i in w.issues.values() if any(query in c for c in i["comments"])])
    s["issues"] = iss

    chat = FastMCP("chat")
    @chat.tool()
    def lookup_user(user_id: str) -> str:
        """Look up a chat user by user id (e.g. u012); returns id and name."""
        return J(w.users.get(user_id, {"error": "not found"}))
    @chat.tool()
    def find_user_by_name(name: str) -> str:
        """Find a chat user by full name."""
        return J(next((u for u in w.users.values() if u["name"] == name), {"error": "not found"}))
    @chat.tool()
    def post_message(user_id: str, text: str) -> str:
        """Send a direct chat message to a user id."""
        if user_id not in w.users: return J({"error": "no such user"})
        w.messages.append({"to": user_id, "text": text}); return J({"ok": True})
    @chat.tool()
    def list_messages(user_id: str) -> str:
        """List messages previously sent to a user."""
        return J([m for m in w.messages if m["to"] == user_id])
    s["chat"] = chat

    logs = FastMCP("logs")
    @logs.tool()
    def query_logs(service: str = "", level: str = "", limit: int = 200, offset: int = 0) -> str:
        """Return raw log lines (ts,service,level,msg) filtered by service (api|auth|billing|search|worker) and level (INFO|WARN|ERROR). Paged, max 500 per call."""
        rows = [l for l in w.logs if (not service or l["service"] == service) and (not level or l["level"] == level)]
        return J({"total": len(rows), "items": rows[offset:offset + min(limit, 500)]})
    @logs.tool()
    def aggregate_logs(group_by: str, level: str = "") -> str:
        """Server-side count of log lines grouped by 'service' or 'level', optionally restricted to a level."""
        from collections import Counter
        return J(dict(Counter(l[group_by] for l in w.logs if not level or l["level"] == level)))
    s["logs"] = logs

    bill = FastMCP("billing")
    @bill.tool()
    def list_invoices(customer: str = "", status: str = "", limit: int = 50, offset: int = 0) -> str:
        """List invoices (id,customer,amount,status,refunded) filtered by customer and status (paid|unpaid|overdue). Paged, max 100."""
        rows = [i for i in w.invoices.values() if (not customer or i["customer"] == customer) and (not status or i["status"] == status)]
        return J({"total": len(rows), "items": rows[offset:offset + min(limit, 100)]})
    @bill.tool()
    def get_invoice(invoice_id: str) -> str:
        """Get one invoice."""
        return J(w.invoices.get(invoice_id, {"error": "not found"}))
    @bill.tool()
    def issue_refund(invoice_id: str, amount: int) -> str:
        """Refund an amount against an invoice."""
        i = w.invoices.get(invoice_id)
        if not i: return J({"error": "not found"})
        i["refunded"] += amount; return J({"ok": True})
    s["billing"] = bill

    docs = FastMCP("docs")
    @docs.tool()
    def list_docs(limit: int = 50, offset: int = 0) -> str:
        """List knowledge-base documents (id,title,author,tags) without bodies. Paged, max 100."""
        rows = [{k: v for k, v in d.items() if k != "body"} for d in w.docs.values()]
        return J({"total": len(rows), "items": rows[offset:offset + min(limit, 100)]})
    @docs.tool()
    def search_docs(query: str) -> str:
        """Full-text search over document titles and bodies; returns matching doc ids and titles."""
        return J([{"id": d["id"], "title": d["title"]} for d in w.docs.values() if query in d["body"] or query in d["title"]])
    @docs.tool()
    def read_doc(doc_id: str) -> str:
        """Read the full text of a document."""
        return J(w.docs.get(doc_id, {"error": "not found"}))
    @docs.tool()
    def append_doc(doc_id: str, text: str) -> str:
        """Append text to the end of a document."""
        d = w.docs.get(doc_id)
        if not d: return J({"error": "not found"})
        d["body"] += " " + text; return J({"ok": True})
    s["docs"] = docs

    cal = FastMCP("calendar_email")
    @cal.tool()
    def list_events(user_id: str, day: int = 0) -> str:
        """List calendar events (user,day,title) for a user, optionally on a given day (1-10)."""
        return J([e for e in w.events if e["user"] == user_id and (not day or e["day"] == day)])
    @cal.tool()
    def create_event(user_id: str, day: int, title: str) -> str:
        """Create a calendar event for a user on a day (1-10)."""
        w.events.append(dict(user=user_id, day=day, title=title)); return J({"ok": True})
    @cal.tool()
    def list_emails(user_id: str, limit: int = 20) -> str:
        """List inbox emails (subject, body) of a user."""
        return J([e for e in w.emails_inbox if e["to"] == user_id][:limit])
    @cal.tool()
    def send_email(to: str, subject: str, body: str) -> str:
        """Send an email to an address."""
        w.emails_sent.append(dict(to=to, subject=subject, body=body)); return J({"ok": True})
    s["calendar_email"] = cal

    crm = FastMCP("crm")
    @crm.tool()
    def query_accounts(segment: str = "", stage: str = "", limit: int = 50, offset: int = 0) -> str:
        """Query CRM accounts by segment (smb|mid|ent) and stage (lead|trial|customer|churned). Paged, max 100."""
        rows = [a for a in w.accounts.values() if (not segment or a["segment"] == segment) and (not stage or a["stage"] == stage)]
        return J({"total": len(rows), "items": rows[offset:offset + min(limit, 100)]})
    @crm.tool()
    def get_account(account_id: str) -> str:
        """Get one CRM account."""
        return J(w.accounts.get(account_id, {"error": "not found"}))
    @crm.tool()
    def update_account(account_id: str, stage: str = "", owner: str = "") -> str:
        """Update a CRM account's stage and/or owner (user id)."""
        a = w.accounts.get(account_id)
        if not a: return J({"error": "not found"})
        if stage: a["stage"] = stage
        if owner: a["owner"] = owner
        return J({"ok": True})
    s["crm"] = crm

    files = FastMCP("files")
    @files.tool()
    def list_files(prefix: str = "") -> str:
        """List file paths starting with a prefix (e.g. 'reports/q1')."""
        return J(sorted(p for p in w.files if p.startswith(prefix)))
    @files.tool()
    def read_file(path: str) -> str:
        """Read a text file."""
        return w.files.get(path, "ERROR: not found")
    @files.tool()
    def write_file(path: str, content: str) -> str:
        """Write a text file."""
        w.files[path] = content; return J({"ok": True})
    s["files"] = files

    dep = FastMCP("deployments")
    @dep.tool()
    def list_deployments(service: str = "", env: str = "", status: str = "", limit: int = 50, offset: int = 0) -> str:
        """List deployments filtered by service, env (prod|staging) and status (success|failed). Paged, max 100."""
        rows = [d for d in w.deploys.values() if (not service or d["service"] == service) and (not env or d["env"] == env) and (not status or d["status"] == status)]
        return J({"total": len(rows), "items": rows[offset:offset + min(limit, 100)]})
    @dep.tool()
    def get_deployment(deployment_id: str) -> str:
        """Get one deployment."""
        return J(w.deploys.get(deployment_id, {"error": "not found"}))
    @dep.tool()
    def rollback_deployment(deployment_id: str) -> str:
        """Roll back a deployment."""
        d = w.deploys.get(deployment_id)
        if not d: return J({"error": "not found"})
        d["rolled_back"] = True; return J({"ok": True})
    s["deployments"] = dep

    hr = FastMCP("hr")
    @hr.tool()
    def get_person(user_id: str) -> str:
        """HR record for a person: name, email, team, manager (user id, null for the CEO)."""
        return J(w.users.get(user_id, {"error": "not found"}))
    @hr.tool()
    def list_team(team: str) -> str:
        """List members (user ids and names) of a team (platform|data|growth|security|support)."""
        return J([{"id": u["id"], "name": u["name"]} for u in w.users.values() if u["team"] == team])
    @hr.tool()
    def get_team_lead(team: str) -> str:
        """Return the user id of a team's lead."""
        return J({"team": team, "lead": w.team_lead.get(team)})
    s["hr"] = hr

    inv = FastMCP("inventory")
    @inv.tool()
    def list_skus(limit: int = 50, offset: int = 0) -> str:
        """List SKUs with stock levels. Paged, max 100."""
        rows = list(w.skus.values()); return J({"total": len(rows), "items": rows[offset:offset + min(limit, 100)]})
    @inv.tool()
    def stock_level(sku: str) -> str:
        """Stock level of one SKU."""
        return J(w.skus.get(sku, {"error": "not found"}))
    @inv.tool()
    def list_orders(status: str = "", limit: int = 50, offset: int = 0) -> str:
        """List orders (id,sku,qty,status new|shipped|cancelled). Paged, max 100."""
        rows = [o for o in w.orders.values() if not status or o["status"] == status]
        return J({"total": len(rows), "items": rows[offset:offset + min(limit, 100)]})
    @inv.tool()
    def restock(sku: str, quantity: int) -> str:
        """Add quantity units to a SKU's stock."""
        k = w.skus.get(sku)
        if not k: return J({"error": "not found"})
        k["stock"] += quantity; return J({"ok": True})
    s["inventory"] = inv

    sup = FastMCP("support")
    @sup.tool()
    def list_tickets(status: str = "", priority: str = "", limit: int = 50, offset: int = 0) -> str:
        """List support tickets filtered by status (open|pending|closed) and priority (low|med|high). Paged, max 100."""
        rows = [t for t in w.tickets.values() if (not status or t["status"] == status) and (not priority or t["priority"] == priority)]
        return J({"total": len(rows), "items": rows[offset:offset + min(limit, 100)]})
    @sup.tool()
    def get_ticket(ticket_id: str) -> str:
        """Get one support ticket."""
        return J(w.tickets.get(ticket_id, {"error": "not found"}))
    @sup.tool()
    def triage_ticket(ticket_id: str, priority: str) -> str:
        """Set a ticket's priority (low|med|high)."""
        t = w.tickets.get(ticket_id)
        if not t: return J({"error": "not found"})
        t["priority"] = priority; return J({"ok": True})
    @sup.tool()
    def assign_ticket(ticket_id: str, user_id: str) -> str:
        """Assign a ticket to a user id."""
        t = w.tickets.get(ticket_id)
        if not t: return J({"error": "not found"})
        t["assignee"] = user_id; return J({"ok": True})
    s["support"] = sup
    return s
