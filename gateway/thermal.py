"""Self-throttle: pause new work while the SoC/GPU is hot, so latency measurements are not taken under thermal throttling."""
import glob, time, subprocess, asyncio
LIMIT_C = 84
def max_temp():
    m = 0
    for f in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try: m = max(m, int(open(f).read()) // 1000)
        except Exception: pass
    return m
def wait_cool_sync(limit=LIMIT_C, poll=10):
    waited = 0
    while max_temp() >= limit: time.sleep(poll); waited += poll
    return waited
async def wait_cool(limit=LIMIT_C, poll=10):
    waited = 0
    while max_temp() >= limit: await asyncio.sleep(poll); waited += poll
    return waited
