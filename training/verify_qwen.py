"""Verification of Nemotron-written data by Qwen (different family): (1) paraphrase fidelity, (2) alias fidelity, (3) gold-tool label audit.
Qwen runs with thinking off at temperature 0; each check is a strict yes/no or JSON."""
import json, re, sys, concurrent.futures as cf
sys.path.insert(0, ".")
from openai import OpenAI
Q = OpenAI(base_url="http://localhost:8888/v1", api_key="x", timeout=300)
EB = {"chat_template_kwargs": {"enable_thinking": False}}
def ask(p, n=300):
    r = Q.chat.completions.create(model="Qwen3.8-27B", messages=[{"role": "user", "content": p}], temperature=0, max_tokens=n, extra_body=EB)
    return (r.choices[0].message.content or "").strip()
def yn(t): return t.lower().startswith("yes")

def check_para(orig, para):
    a = ask(f"Request A: {orig}\nRequest B: {para}\n\nDo A and B ask an assistant to do exactly the same thing, with the same parameters, no extra requirements and nothing missing? Answer 'yes' or 'no' only.", 5)
    return yn(a)
def check_alias(name, desc, alias):
    a = ask(f"Tool 1: {name} - {desc}\nTool 2: {alias['name']} - {alias['description']}\n\nDo these two tool definitions describe the same functionality (same operation, same kind of filters)? Answer 'yes' or 'no' only.", 5)
    return yn(a)
def audit_labels(instruction, gold, catalog_desc):
    lst = "\n".join(f"- {n}: {catalog_desc[n]}" for n in gold)
    a = ask(f"Task: {instruction}\n\nThese tools are claimed to be the tools needed to complete the task:\n{lst}\n\nIs it plausible that a competent agent needs ALL of these tools and that no other kind of tool is required? Reply JSON only: {{\"all_needed\": true/false, \"missing_capability\": \"...or empty\"}}", 120)
    try: return json.loads(re.search(r"\{.*\}", a, re.S).group(0))
    except Exception: return {"all_needed": None, "raw": a[:100]}
