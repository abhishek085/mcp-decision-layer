import sys; sys.path.insert(0, ".")
from worlds.world import World
from tasks.templates import build_suite
bad = 0
for salt, seed in [("dev", 0), ("dev", 1)]:
    base = World(seed, "medium", salt)
    for t in build_suite(base):
        a, b = World(seed, "medium", salt), World(seed, "medium", salt)
        t_a = [x for x in build_suite(a) if x.id == t.id][0]; t_b = [x for x in build_suite(b) if x.id == t.id][0]
        ra, rb = t_a.solve(a), t_b.solve(b)
        ok = t_a.verify(a, ra) and a.state_hash() == b.state_hash()
        neg = t_a.verify(World(seed, "medium", salt), "zzz")   # unsolved baseline must NOT pass (except no-op tasks)
        bad += (not ok)
        print(salt, seed, t.id, "solvable+deterministic" if ok else "FAIL", "| noop-passes" if neg else "")
print("FAILS:", bad)
