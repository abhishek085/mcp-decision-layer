#!/bin/bash
# usage: watch_run.sh <pidfile> <trace.jsonl> <total_runs>
# Emits: PROGRESS every 5 min; ALERT on stall (>6 min no new rows), SoC>=90C, container paused/down; DONE on exit.
pid=$(cat "$1"); f=$2; total=$3; last=-1; last_change=$(date +%s); tick=0
while true; do
  n=$(wc -l < "$f" 2>/dev/null || echo 0); now=$(date +%s)
  [ "$n" != "$last" ] && { last=$n; last_change=$now; }
  m=0; for z in /sys/class/thermal/thermal_zone*/temp; do v=$(( $(cat $z)/1000 )); [ $v -gt $m ] && m=$v; done
  st=$(docker ps --format '{{.Names}}={{.Status}}' | grep -E 'osj-jev|qwen38|mdl-' | grep -E 'Paused' | tr '\n' ' ')
  down=""; for c in ${WATCH_CONTAINERS:-qwen38-27b-tf osj-jev-vllm}; do docker ps --format '{{.Names}}' | grep -qx $c || down="$down $c"; done
  if ! kill -0 $pid 2>/dev/null; then echo "DONE: process exited; rows=$n/$total"; exit 0; fi
  [ $((now-last_change)) -gt 360 ] && { echo "ALERT stall: no new rows for $(( (now-last_change)/60 )) min (rows=$n/$total, soc=${m}C)"; last_change=$now; }
  [ $m -ge 90 ] && echo "ALERT hot: SoC ${m}C"
  [ -n "$st" ] && echo "ALERT paused: $st"
  [ -n "$down" ] && echo "ALERT container down:$down"
  tick=$((tick+1)); [ $((tick % 10)) -eq 0 ] && echo "PROGRESS rows=$n/$total soc=${m}C"
  sleep 30
done
