#!/bin/bash
# usage: gguf_serve.sh <variant: BF16|Q8_0|Q4_K_M>   (starts llama-server on :8402; gateway on :8403 is started once separately)
V=$1; G=/home/admin/llm-workspace/mcp-decision-layer/training/gguf/spark-s1-mcp-router-4b-r1-$V.gguf
LL=/home/admin/llm-workspace/llama.cpp/build-cuda/bin
LD_LIBRARY_PATH=$LL:$LD_LIBRARY_PATH nohup $LL/llama-server -m $G --host 127.0.0.1 --port 8402 -ngl 99 -c 32768 --parallel 8 > /home/admin/llm-workspace/mcp-decision-layer/training/gguf/server_$V.log 2>&1 &
echo $! > /home/admin/llm-workspace/mcp-decision-layer/training/gguf/server.pid
