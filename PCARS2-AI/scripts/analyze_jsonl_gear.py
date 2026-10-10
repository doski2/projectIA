"""Análisis rápido de marcha en universal_teacher.jsonl."""
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "data/universal_teacher.jsonl")
rows = [json.loads(l) for l in p.read_text(encoding="utf-8").strip().splitlines()]


def g(r):
    return r["obs"][16]


def ld(r):
    return r["lap_distance"]


def thr(r):
    return (r["action"][0] + 1) / 2


def brk(r):
    return (r["action"][1] + 1) / 2


print("lines", len(rows))
print("neutral%", 100 * sum(1 for r in rows if g(r) < 0.05) / len(rows))
print("reasons", Counter(r["teacher_reason"] for r in rows).most_common(8))

for lo, hi, name in [(0, 150, "0-150"), (150, 300, "150-300"), (300, 600, "300-600")]:
    seg = [r for r in rows if lo <= ld(r) < hi]
    if not seg:
        continue
    n = sum(1 for r in seg if g(r) < 0.05)
    print(
        name,
        "neutral%",
        round(100 * n / len(seg), 1),
        "neutral reasons",
        Counter(r["teacher_reason"] for r in seg if g(r) < 0.05).most_common(4),
    )

# Transitions into neutral after ld>140
prev_g = None
print("\n--- entries to neutral (ld>140) ---")
for i, r in enumerate(rows):
    gn = g(r) < 0.05
    if ld(r) < 140:
        prev_g = gn
        continue
    if gn and not prev_g:
        print(
            i,
            f"ld={ld(r):.0f}",
            "from gear_norm",
            round(rows[i - 1]["obs"][16], 3) if i else "?",
            "->",
            r["teacher_reason"],
            f"spd={r['obs'][0]*50:.1f}",
        )
    prev_g = gn

# engage_first neutral without progress (gear stays 0 for 50+ ticks)
runs = []
s = None
for i, r in enumerate(rows):
    if g(r) < 0.05 and r["teacher_reason"] == "engage_first":
        if s is None:
            s = i
    else:
        if s is not None:
            runs.append((i - s, s, i - 1))
            s = None
if s:
    runs.append((len(rows) - s, s, len(rows) - 1))
runs.sort(reverse=True)
print("\n--- longest engage_first @ neutral ---")
for length, a, b in runs[:5]:
    seg = rows[a : b + 1]
    print(
        length,
        "ticks",
        f"ld {ld(seg[0]):.0f}-{ld(seg[-1]):.0f}",
        f"thr mean {statistics.mean(thr(x) for x in seg):.2f}",
        f"rpm mean {statistics.mean(x['obs'][15] for x in seg):.2f}",
        f"game_thr mean {statistics.mean(x['obs'][13] for x in seg):.2f}",
    )

print("\n--- timeline 2480-2580 step 20 ---")
for i in range(2480, min(2580, len(rows)), 20):
    r = rows[i]
    print(
        i,
        f"ld={ld(r):.0f}",
        f"g={g(r):.2f}",
        r["teacher_reason"],
        f"thr={thr(r):.2f}",
        f"rpm={r['obs'][15]:.2f}",
        f"gt={r['obs'][13]:.2f}",
    )

# neutral + NOT engage_first
bad = [r for r in rows if g(r) < 0.05 and r["teacher_reason"] != "engage_first"]
print("\nneutral not engage_first", len(bad), Counter(r["teacher_reason"] for r in bad))
