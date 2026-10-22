"""Phase 1 smoke tests for one OpenAI-compatible endpoint."""
import sys, time, json, concurrent.futures as cf
from openai import OpenAI

def run(base, model, tag):
    c = OpenAI(base_url=base, api_key="x", timeout=300)
    out = {"tag": tag, "model": model}
    tools = [{"type": "function", "function": {"name": "get_weather", "description": "Get weather for a city",
              "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
    # 1 native function calling, 10 trials
    ok = 0; lat = []
    for i in range(10):
        city = ["Paris", "Oslo", "Lima", "Pune", "Rome"][i % 5]
        t = time.time()
        try:
            r = c.chat.completions.create(model=model, messages=[{"role": "user", "content": f"What's the weather in {city}?"}],
                                          tools=tools, temperature=0, max_tokens=512)
            tc = r.choices[0].message.tool_calls
            if tc and tc[0].function.name == "get_weather" and json.loads(tc[0].function.arguments).get("city") == city: ok += 1
        except Exception as e:
            out["fc_err"] = str(e)[:200]
        lat.append(time.time() - t)
    out["fc_ok_of_10"] = ok; out["fc_lat_s"] = round(sum(lat) / len(lat), 2)
    # 2 script writing
    t = time.time()
    r = c.chat.completions.create(model=model, temperature=0, max_tokens=1024, messages=[{"role": "user",
        "content": "Write a Python function solve(xs) returning the sum of squares of the even numbers in xs. Output only a ```python block."}])
    txt = r.choices[0].message.content or ""
    code = txt.split("```python")[-1].split("```")[0] if "```" in txt else txt
    ns = {}
    try:
        exec(code, ns); out["script_ok"] = ns["solve"]([1, 2, 3, 4]) == 20
    except Exception as e:
        out["script_ok"] = False; out["script_err"] = str(e)[:100]
    out["script_s"] = round(time.time() - t, 2)
    # 3 throughput: single stream decode speed
    t = time.time()
    r = c.chat.completions.create(model=model, temperature=0, max_tokens=300, messages=[{"role": "user", "content": "Count from 1 to 200 separated by spaces."}])
    out["decode_tok_s_single"] = round(r.usage.completion_tokens / (time.time() - t), 1)
    # 4 concurrency 8
    def one(_):
        r = c.chat.completions.create(model=model, temperature=0, max_tokens=200, messages=[{"role": "user", "content": "Count from 1 to 150 separated by spaces."}])
        return r.usage.completion_tokens
    t = time.time()
    with cf.ThreadPoolExecutor(8) as ex: n = sum(ex.map(one, range(8)))
    out["decode_tok_s_c8_aggregate"] = round(n / (time.time() - t), 1)
    # 5 long-context ~30K tokens of schemas
    fake = []
    for i in range(200):
        fake.append({"type": "function", "function": {"name": f"tool_{i}_do_thing", "description": f"Tool number {i}. " + "Performs an operation on resource of kind %d with various options. " % i * 3,
            "parameters": {"type": "object", "properties": {f"p{j}": {"type": "string", "description": "parameter %d of tool %d" % (j, i)} for j in range(6)}, "required": ["p0"]}}})
    fake.append(tools[0])
    t = time.time()
    try:
        r = c.chat.completions.create(model=model, temperature=0, max_tokens=256, tools=fake,
            messages=[{"role": "user", "content": "What's the weather in Oslo?"}])
        tc = r.choices[0].message.tool_calls
        out["long_ctx_prompt_tokens"] = r.usage.prompt_tokens
        out["long_ctx_pick_ok"] = bool(tc and tc[0].function.name == "get_weather")
    except Exception as e:
        out["long_ctx_err"] = str(e)[:200]
    out["long_ctx_s"] = round(time.time() - t, 2)
    return out

if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1], sys.argv[2], sys.argv[3]), indent=1))
