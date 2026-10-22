import sys; sys.path.insert(0, ".")
from worlds.world import World
from tasks.templates import build_suite, build_suite_raw
bad = 0
for salt, seed, size in [("dev", 0, "medium"), ("dev", 1, "medium"), ("dev", 2, "medium"), ("dev", 0, "large")]:
    w = World(seed, size, salt); raw = {t.id for t in build_suite_raw(w)}; kept = build_suite(w)
    for t in kept:
        wa, wb = World(seed, size, salt), World(seed, size, salt)
        ok = t.verify(wa, t.solve(wa)); t.solve(wb); ok = ok and wa.state_hash() == wb.state_hash()
        bad += (not ok)
        if not ok: print("FAIL", salt, seed, size, t.id)
    print(salt, seed, size, "raw", len(raw), "kept", len(kept), "dropped(vacuous/unsolvable):", sorted(raw - {t.id for t in kept}), "unique ids:", len({t.id for t in kept}) == len(kept))
print("FAILS:", bad)
