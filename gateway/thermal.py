"""Self-throttle: pause new work while the SoC/GPU is hot (the machine's own thermal guard pauses osj-* containers at >=91C; we stay below)."""
import glob, time, subprocess, asyncio
LIMIT_C = 86
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
