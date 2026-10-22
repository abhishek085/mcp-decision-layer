import time, threading, json, sys
from openai import OpenAI
Q = OpenAI(base_url="http://localhost:8888/v1", api_key="x", timeout=300); G = OpenAI(base_url="http://localhost:8002/v1", api_key="x", timeout=300)
P = [{"role": "user", "content": "Count from 1 to 300 separated by spaces."}]
def qwen_rate(n=3):
    rs = []
    for _ in range(n):
        t = time.time(); r = Q.chat.completions.create(model="Qwen3.8-27B", messages=P, temperature=0, max_tokens=400, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        rs.append(r.usage.completion_tokens / (time.time() - t))
    return round(sum(rs) / len(rs), 1)
def gemma_rate():
    t = time.time(); r = G.chat.completions.create(model="gemma", messages=P, temperature=0, max_tokens=400)
    return round(r.usage.completion_tokens / (time.time() - t), 1)
res = {"qwen_alone_gemma_idle": qwen_rate(), "gemma_alone_qwen_idle": gemma_rate()}
stop = False
def load():
    while not stop:
        try: G.chat.completions.create(model="gemma", messages=P, temperature=0, max_tokens=400)
        except Exception: pass
ths = [threading.Thread(target=load) for _ in range(4)]; [t.start() for t in ths]; time.sleep(3)
res["qwen_while_gemma_busy(4 streams)"] = qwen_rate()
stop = True; [t.join() for t in ths]
# reverse: gemma while qwen busy
stop2 = False
def loadq():
    while not stop2:
        try: Q.chat.completions.create(model="Qwen3.8-27B", messages=P, temperature=0, max_tokens=400, extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        except Exception: pass
ths = [threading.Thread(target=loadq) for _ in range(4)]; [t.start() for t in ths]; time.sleep(3)
res["gemma_while_qwen_busy(4 streams)"] = gemma_rate()
stop2 = True; [t.join() for t in ths]
print(json.dumps(res, indent=1))
