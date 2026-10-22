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
        self._snap = self.state_hash()

    def _state(self):
        return dict(issues=self.issues, messages=self.messages, invoices=self.invoices)
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
    return s
