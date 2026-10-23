#!/bin/bash
cd /home/admin/llm-workspace/mcp-decision-layer
for V in "$@"; do
  kill $(cat training/gguf/server.pid) 2>/dev/null; sleep 6
  bench/gguf_serve.sh $V
  for i in $(seq 1 60); do sleep 3; curl -sf -m 2 localhost:8402/health >/dev/null 2>&1 && break; done
  .venv/bin/python bench/toolsel2.py --url http://localhost:8403/v1/decide --label "GGUF $V via llama.cpp" --ndist 0 --out traces/toolsel2_gguf_${V}_n0.jsonl > traces/toolsel2_gguf_$V.out 2>&1
  .venv/bin/python bench/gguf_compare.py traces/toolsel2_router_v3_n0.jsonl traces/toolsel2_gguf_${V}_n0.jsonl "GGUF $V" > traces/gguf_compare_$V.txt 2>&1
done
echo CHAIN_DONE
