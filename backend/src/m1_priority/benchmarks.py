"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
benchmarks.py -- measured timings and complexity table for the report.

Every number returned here is measured on the machine running the app when the
benchmark is requested (no hard-coded figures).  Results are cached because a
full run touches ~25,000 plots several times.
"""
from __future__ import annotations

import random
import time

from .buffers import CircularQueue, SlidingWindowTrend
from .heap import IndexedMaxHeap, heap_sort
from .schema import SCORE_MAX
from .sorting import bench_sort_algorithms, counting_sort_records, sort_scores


def _ms(fn, *args, **kwargs) -> tuple[float, object]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0, result


def bench_heap(n: int = 25_000, seed: int = 42) -> dict:
    """Build, insert, peeking, update-key and extract-max on the indexed heap."""
    rng = random.Random(seed)
    scores = [rng.randint(0, SCORE_MAX) for _ in range(n)]

    build_ms, heap = _ms(lambda: _build_heap(scores))
    peek_ms, _ = _ms(lambda: [heap.peek() for _ in range(10_000)])

    sample = heap.snapshot()[:2_000]
    up_ids = [pid for _, pid in sample]
    t0 = time.perf_counter()
    for i, pid in enumerate(up_ids):
        heap.update_key(pid, rng.randint(0, SCORE_MAX))
    update_ms = (time.perf_counter() - t0) * 1000.0

    # linear-scan baseline: what update-key would cost WITHOUT the index dict
    t0 = time.perf_counter()
    heap_list = heap.snapshot()
    scans = 0
    for i, pid in enumerate(up_ids[:200]):
        for j, (_, p) in enumerate(heap_list):
            scans += 1
            if p == pid:
                break
    naive_ms = (time.perf_counter() - t0) * 1000.0

    drain_ms, drained = _ms(lambda: heap.drain(limit=None, copy=True))

    return {
        "n": n,
        "build_heap_ms": round(build_ms, 2),
        "peek_10000_calls_ms": round(peek_ms, 3),
        "peek_per_call_us": round(peek_ms / 10_000 * 1000, 4),
        "update_key_2000_ms": round(update_ms, 3),
        "update_key_per_call_us": round(update_ms / len(up_ids) * 1000, 3),
        "naive_linear_search_200_ms": round(naive_ms, 3),
        "naive_linear_search_per_call_us": round(naive_ms / 200 * 1000, 3),
        "extract_all_copy_ms": round(drain_ms, 2),
        "extracts": len(drained),
        "heap_depth": heap.depth(),
        "log2_n": round(__import__("math").log2(n), 2),
        "note": "O(1) peek, O(log n) insert/update/extract thanks to plot_id -> index dict",
    }


def _build_heap(scores: list[int]) -> IndexedMaxHeap:
    heap = IndexedMaxHeap()
    for pid, s in enumerate(scores, start=1):
        heap.insert(pid, s)
    return heap


def bench_queue(n: int = 25_000, seed: int = 42) -> dict:
    """Circular ring buffer vs a Python list used as a FIFO.

    Three clearly separated measurements, because a single number here would be
    misleading:

      (a) STEADY STATE -- both structures hold a fixed retention of n/4 while n
          items flow through them.  The list must shift memory with pop(0),
          the ring overwrites one slot.  This is the real workload.
      (b) DRAIN -- emptying a full structure: pop(0) vs a head-pointer move.
      (c) OVERFLOW POLICY -- what happens when producers outrun consumers,
          which a plain list has no answer for at all.

    Honest caveat recorded for the report: collections.deque is implemented in C,
    so it beats a pure-Python ring buffer in wall-clock time.  The ring buffer is
    used here because it is the syllabus data structure, its cost is O(1) by
    construction with no hidden reallocation, and it carries an explicit,
    accounted overflow policy that a list or deque does not.
    """
    import collections
    rng = random.Random(seed)
    data = [(rng.randint(1, 50_000), rng.random()) for _ in range(n)]
    retention = max(1, n // 4)

    # (a) steady state -------------------------------------------------------
    ring = CircularQueue(capacity=retention)
    t0 = time.perf_counter()
    for item in data:
        ring.enqueue(item)
    ring_steady_ms = (time.perf_counter() - t0) * 1000.0

    lst: list = []
    t0 = time.perf_counter()
    for item in data:
        lst.append(item)
        if len(lst) > retention:
            lst.pop(0)                      # O(retention) memmove per item
    list_steady_ms = (time.perf_counter() - t0) * 1000.0

    dq = collections.deque(maxlen=retention)
    t0 = time.perf_counter()
    for item in data:
        dq.append(item)
    cdeque_steady_ms = (time.perf_counter() - t0) * 1000.0

    # (b) drain --------------------------------------------------------------
    full_ring = CircularQueue(capacity=n)
    for item in data:
        full_ring.enqueue(item)
    t0 = time.perf_counter()
    while not full_ring.is_empty():
        full_ring.dequeue()
    ring_drain_ms = (time.perf_counter() - t0) * 1000.0

    full_list = list(data)
    t0 = time.perf_counter()
    while full_list:
        full_list.pop(0)
    list_drain_ms = (time.perf_counter() - t0) * 1000.0

    # (c) overflow -----------------------------------------------------------
    small = CircularQueue(capacity=retention)
    stored = 0
    for item in data:
        stored += 1 if small.enqueue(item) else 0

    return {
        "items": n, "retention": retention,
        "steady_state": {
            "ring_enqueue_ms": round(ring_steady_ms, 3),
            "list_fifo_ms": round(list_steady_ms, 3),
            "collections_deque_ms": round(cdeque_steady_ms, 3),
            "speedup_vs_list": round(list_steady_ms / max(0.0001, ring_steady_ms), 2),
            "ring_dropped": ring.dropped, "list_silently_grows": "no (we added pop(0))",
        },
        "drain": {
            "ring_dequeue_ms": round(ring_drain_ms, 3),
            "list_pop0_ms": round(list_drain_ms, 3),
            "speedup": round(list_drain_ms / max(0.0001, ring_drain_ms), 2),
        },
        "overflow_policy": {
            "capacity": retention, "pushed": small.pushed, "stored": stored,
            "dropped": small.dropped, "retained": len(small),
            "behaviour": "oldest reading overwritten, memory stays bounded, drops counted",
        },
        "caveat": "collections.deque is C-implemented and wins on wall-clock; the ring buffer "
                  "is chosen for O(1) by construction plus an explicit accounted overflow policy.",
        "complexity": "enqueue O(1), dequeue O(1), space O(capacity)",
    }


def bench_trend(windows: int = 4_000, window_size: int = 60, ticks: int = 200, seed: int = 42) -> dict:
    """Deque sliding window vs re-scanning the raw list for every statistics call."""
    rng = random.Random(seed)
    scores = [[rng.randint(0, SCORE_MAX) for _ in range(ticks)] for _ in range(windows)]

    trend = SlidingWindowTrend(window_size=window_size)
    t0 = time.perf_counter()
    for t in range(ticks):
        for plot_id in range(windows):
            trend.push(plot_id, scores[plot_id][t])
    push_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    _ = [trend.rolling_max(i) for i in range(windows)]
    mono_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    for i in range(windows):
        series = trend.series(i)
        _ = max(series)                    # O(window) rescan
    rescan_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "tracked_plots": windows, "window_size": window_size, "ticks": ticks,
        "theoretical_ratio": window_size,
        "push_total_ms": round(push_ms, 2),
        "push_per_call_us": round(push_ms / (windows * ticks) * 1000, 4),
        "rolling_max_monotonic_deque_ms": round(mono_ms, 3),
        "rolling_max_full_rescan_ms": round(rescan_ms, 3),
        "speedup": round(rescan_ms / max(0.001, mono_ms), 2),
        "note": "monotonic deque -> O(1) amortised rolling max instead of O(window) scan",
    }


def bench_scheduler(scheduler, plots, heap, repeats: int = 5) -> dict:
    """Full schedule rebuild (extract-max drain + priority ordering)."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = scheduler.build_schedule(plots, heap, tick=0)
        times.append((time.perf_counter() - t0) * 1000.0)
    return {
        "repeats": repeats,
        "avg_ms": round(sum(times) / len(times), 3),
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
        "seats": result["summary"]["seats_total"],
        "plots_scheduled": result["summary"]["seats_filled"],
        "note": "O(k log n) extract-max over a heap COPY; live heap untouched",
    }


def bench_pipeline(sim, ticks: int = 10) -> dict:
    """Cost of one full simulation tick on the live 25,000-plot farm."""
    times = []
    for _ in range(ticks):
        stats = sim.tick_once()
        times.append(stats["elapsed_ms"])
    return {
        "plots": len(sim.plots),
        "ticks_measured": ticks,
        "avg_tick_ms": round(sum(times) / len(times), 2),
        "min_tick_ms": round(min(times), 2),
        "max_tick_ms": round(max(times), 2),
        "per_plot_us": round(sum(times) / len(times) / max(1, len(sim.plots)) * 1000, 3),
        "stages": "sensor update -> score -> heap update-key -> deque trend -> ingest drain -> slot irrigation -> schedule",
        "note": "one tick = 25,000 score recomputations + 25,000 heap update-key calls",
    }


def bench_board(sim, limit: int = 60) -> dict:
    """Priority-board query cost (heap copy + counting sort of the candidate pool)."""
    out = {"limit": limit}
    for algo in ("counting", "heap"):
        t0 = time.perf_counter()
        payload = sim.top_plots(limit=limit, algorithm=algo)
        out[algo] = {
            "total_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "sort_ms": payload["sort_ms"],
            "candidates": payload["candidates"],
        }
    return out


def bench_quadtree_reference() -> list[dict]:
    """M2 comparison points printed alongside M1 numbers (informational only)."""
    return [
        {"structure": "Quad-Tree range query", "owner": "Member 2", "complexity": "O(sqrt(n) + k) typical",
         "note": "compare against this module's heap + counting sort pipeline"},
        {"structure": "BFS / DFS over canal graph", "owner": "Member 2", "complexity": "O(V + E)",
         "note": "owner publishes measured figures"},
    ]


COMPLEXITY_TABLE = [
    {"structure": "Indexed Max-Heap", "operation": "peek / insert / update-key / extract-max",
     "complexity": "O(1) / O(log n) / O(log n) / O(log n)", "member": 1, "used_for": "priority queue of stressed plots"},
    {"structure": "Circular Queue", "operation": "enqueue / dequeue",
     "complexity": "O(1) / O(1), fixed memory", "member": 1, "used_for": "sensor ingest buffer"},
    {"structure": "Deque (monotonic)", "operation": "push / rolling max / trend",
     "complexity": "O(1) amortised / O(1) / O(1)", "member": 1, "used_for": "sliding-window drying trend"},
    {"structure": "Dictionary", "operation": "plot_id -> plot / plot_id -> heap index",
     "complexity": "O(1) average", "member": 1, "used_for": "record lookup + heap indexing"},
    {"structure": "Counting sort", "operation": "order 0..1000 integer scores",
     "complexity": "O(n + k), k = 1001, stable", "member": 1, "used_for": "priority board ordering"},
    {"structure": "Heap sort", "operation": "order arbitrary keys",
     "complexity": "O(n log n) worst case, O(1) space", "member": 1, "used_for": "fallback when key domain is unknown"},
    {"structure": "Insertion sort", "operation": "re-sort nearly-sorted run list",
     "complexity": "O(n + inversions) ~ O(n)", "member": 1, "used_for": "between-tick repair"},
    {"structure": "Bubble sort", "operation": "O(n^2) baseline",
     "complexity": "O(n^2) worst, O(n) best with early exit", "member": 1, "used_for": "benchmark baseline only"},
]


def run_all(scheduler=None, plots=None, heap=None, sim=None,
            sizes=(1_000, 5_000, 10_000, 25_000), seed: int = 42) -> dict:
    """Everything the Benchmark panel shows, in one call."""
    t_start = time.perf_counter()
    out = {
        "generated_at_tick": None,
        "sorts": bench_sort_algorithms(sizes=sizes, seed=seed),
        "heap": bench_heap(seed=seed),
        "circular_queue": bench_queue(seed=seed),
        "deque_trend": bench_trend(seed=seed),
        "complexity_table": COMPLEXITY_TABLE,
        "member2_reference": bench_quadtree_reference(),
    }
    if scheduler is not None and plots is not None and heap is not None:
        out["scheduler"] = bench_scheduler(scheduler, plots, heap)
    if sim is not None:
        out["pipeline"] = bench_pipeline(sim, ticks=5)
        out["priority_board"] = bench_board(sim, limit=60)
    out["total_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
    return out


if __name__ == "__main__":
    import json
    res = run_all(sizes=(1_000, 5_000))
    print(json.dumps(res["heap"], indent=2))
    print(json.dumps(res["circular_queue"], indent=2))
    print(json.dumps(res["deque_trend"], indent=2))
    for row in res["sorts"]["rows"]:
        print(row["n"], {k: (v.get("time_ms") if isinstance(v, dict) else v) for k, v in row["results"].items()})
