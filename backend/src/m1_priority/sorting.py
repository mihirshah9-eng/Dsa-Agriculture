"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
sorting.py -- Counting sort, Bubble sort, Insertion sort, Heap sort (+ stats).

Where each sort is actually used in this module (not decorative):

    Counting sort  -> the DEFAULT ordering of the priority board / pump run-list.
                      Stress scores are integers in [0, 1000], so we can sort
                      n plots in O(n + k) with k = 1001, which beats every
                      comparison sort on 25,000 plots.  Stable, so equal-score
                      plots keep their previous relative order.
    Heap sort      -> the fallback when the score domain is not known to be
                      small (e.g. floating-point "benefit per litre" from M3),
                      and it is the only one of the four with O(n log n)
                      worst case and O(1) extra space.
    Insertion sort -> repairs an ALREADY-ALMOST-SORTED run list between ticks:
                      when only a handful of plots change score, re-sorting
                      from scratch is wasteful; insertion sort on the near-sorted
                      array is O(n + inversions), i.e. ~O(n) in practice.
    Bubble sort    -> deliberately kept as the O(n^2) baseline for the benchmark
                      table, with the early-exit optimisation noted.  It is NOT
                      used in the scheduling hot path.

Every function returns (sorted_list, stats) where useful, and `bench_sort_algorithms`
produces the numbers that go into the report.
"""
from __future__ import annotations

import time

from .heap import heap_sort


# ---------------------------------------------------------------------------
# 1) Counting sort -- O(n + k), k = value range (1001), stable
# ---------------------------------------------------------------------------
def counting_sort(values: list[int], max_value: int = 1000,
                  descending: bool = True, count_comparisons: bool = True) -> tuple[list[int], dict]:
    n = len(values)
    if n == 0:
        return [], {"algorithm": "counting", "n": 0, "time_ms": 0.0, "comparisons": 0, "swaps": 0}

    t0 = time.perf_counter()
    counts = [0] * (max_value + 1)
    for v in values:                              # O(n)
        counts[v if v <= max_value else max_value] += 1
    for i in range(1, max_value + 1):             # O(k) prefix sums
        counts[i] += counts[i - 1]

    out = [0] * n
    if descending:
        # offset[i] = number of elements that must come BEFORE bucket i
        offset = [n - counts[i] for i in range(max_value + 1)]
        for v in values:                          # O(n), stable
            b = v if v <= max_value else max_value
            out[offset[b]] = v
            offset[b] += 1
    else:
        offset = [counts[i - 1] if i else 0 for i in range(max_value + 1)]
        for v in values:
            b = v if v <= max_value else max_value
            out[offset[b]] = v
            offset[b] += 1
    elapsed = (time.perf_counter() - t0) * 1000.0
    return out, {
        "algorithm": "counting", "n": n, "time_ms": round(elapsed, 4),
        "comparisons": 0 if count_comparisons else 0,   # counting sort compares nothing
        "swaps": 0, "extra_space": f"O(n + k), k={max_value + 1}",
    }


def counting_sort_records(records: list[tuple[int, int]], max_value: int = 1000) -> list[tuple[int, int]]:
    """Sort (score, plot_id) records by score descending, stable on ties.

    Stable + descending: we walk the buckets from the top so that equal scores
    keep the order they had in `records` (which the heap produced).
    """
    if not records:
        return []
    buckets: list[list[tuple[int, int]]] = [[] for _ in range(max_value + 1)]
    for rec in records:
        s = rec[0]
        buckets[s if 0 <= s <= max_value else (0 if s < 0 else max_value)].append(rec)
    out: list[tuple[int, int]] = []
    for b in range(max_value, -1, -1):            # descending bucket scan
        out.extend(buckets[b])
    return out


# ---------------------------------------------------------------------------
# 2) Bubble sort -- O(n^2) baseline, early-exit version
# ---------------------------------------------------------------------------
def bubble_sort(values: list[int], descending: bool = True) -> tuple[list[int], dict]:
    arr = list(values)
    n = len(arr)
    comparisons = swaps = 0
    t0 = time.perf_counter()
    for i in range(n - 1):
        swapped = False                            # early-exit optimisation
        for j in range(n - 1 - i):
            comparisons += 1
            a, b = arr[j], arr[j + 1]
            if (a < b) if descending else (a > b):
                arr[j], arr[j + 1] = b, a
                swaps += 1
                swapped = True
        if not swapped:                            # already sorted -> O(n)
            break
    elapsed = (time.perf_counter() - t0) * 1000.0
    return arr, {"algorithm": "bubble", "n": n, "time_ms": round(elapsed, 4),
                 "comparisons": comparisons, "swaps": swaps, "extra_space": "O(1)"}


# ---------------------------------------------------------------------------
# 3) Insertion sort -- the "repair a nearly sorted list" sort
# ---------------------------------------------------------------------------
def insertion_sort(values: list[int], descending: bool = True) -> tuple[list[int], dict]:
    arr = list(values)
    comparisons = swaps = 0
    t0 = time.perf_counter()
    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        while j >= 0:
            comparisons += 1
            if (arr[j] < key) if descending else (arr[j] > key):
                arr[j + 1] = arr[j]
                swaps += 1
                j -= 1
            else:
                break
        arr[j + 1] = key
    elapsed = (time.perf_counter() - t0) * 1000.0
    return arr, {"algorithm": "insertion", "n": len(arr), "time_ms": round(elapsed, 4),
                 "comparisons": comparisons, "swaps": swaps, "extra_space": "O(1)"}


def insertion_sort_nearly_sorted(values: list[int], descending: bool = True) -> tuple[list[int], dict]:
    """Same algorithm, documented wrapper used for the 'perturbed list' benchmark."""
    sorted_arr, stats = insertion_sort(values, descending=descending)
    stats["note"] = "nearly-sorted input -> O(n + inversions)"
    return sorted_arr, stats


# ---------------------------------------------------------------------------
# 4) Heap sort -- O(n log n) worst case, O(1) space
# ---------------------------------------------------------------------------
def heap_sort_scores(values: list[int], descending: bool = True) -> tuple[list[int], dict]:
    t0 = time.perf_counter()
    out = heap_sort(values, descending=descending)
    elapsed = (time.perf_counter() - t0) * 1000.0
    n = len(values)
    # comparisons for heap sort are data dependent; report the theoretical bound
    return out, {"algorithm": "heap", "n": n, "time_ms": round(elapsed, 4),
                 "comparisons": "~2n log n (bound)", "swaps": "~n log n (bound)",
                 "extra_space": "O(1), in-place"}


# ---------------------------------------------------------------------------
# Facade used by the rest of the module + the benchmark panel
# ---------------------------------------------------------------------------
ALGORITHMS = {
    "counting": lambda v: counting_sort(v)[0],
    "bubble": lambda v: bubble_sort(v)[0],
    "insertion": lambda v: insertion_sort(v)[0],
    "heap": lambda v: heap_sort_scores(v)[0],
}


def sort_scores(values: list[int], algorithm: str = "counting") -> tuple[list[int], dict]:
    """One call, any algorithm, with timing stats attached."""
    if algorithm == "counting":
        return counting_sort(values)
    if algorithm == "bubble":
        return bubble_sort(values)
    if algorithm == "insertion":
        return insertion_sort(values)
    if algorithm == "heap":
        return heap_sort_scores(values)
    raise ValueError(f"unknown algorithm: {algorithm}")


def make_nearly_sorted(values: list[int], swapped_pairs: int = 25) -> list[int]:
    """Take a sorted list and perturb it slightly -- the realistic between-tick case."""
    arr = sorted(values, reverse=True)
    step = max(1, len(arr) // max(1, swapped_pairs))
    for i in range(0, len(arr) - step, step):
        arr[i], arr[i + step] = arr[i + step], arr[i]
    return arr


def bench_sort_algorithms(sizes=(1_000, 5_000, 10_000, 25_000),
                          seed: int = 42, quadratic_cap: int = 5_000) -> dict:
    """Benchmark table for the report.

    Bubble/insertion sort are O(n^2); they are skipped above `quadratic_cap`
    (the projected cost is shown instead) so that a UI click cannot hang the
    Flask worker for tens of seconds.
    """
    import random

    rng = random.Random(seed)
    rows = []
    for n in sizes:
        data = [rng.randint(0, 1000) for _ in range(n)]
        row = {"n": n, "results": {}}
        for name in ("counting", "heap", "insertion", "bubble"):
            if name in ("bubble", "insertion") and n > quadratic_cap:
                row["results"][name] = {
                    "skipped": True,
                    "reason": f"O(n^2) skipped above n={quadratic_cap}",
                    "projected_ms": _project_quadratic(cap=quadratic_cap, n=n, seed=seed),
                }
                continue
            _, stats = sort_scores(data, name)
            stats.pop("algorithm", None)
            row["results"][name] = stats
        rows.append(row)

    # nearly-sorted case: insertion sort should shine
    n = min(25_000, max(sizes))
    base = [rng.randint(0, 1000) for _ in range(n)]
    nearly = make_nearly_sorted(base, swapped_pairs=25)
    _, insert_stats = insertion_sort(nearly, descending=True)
    _, counting_stats = counting_sort(nearly)
    rows.append({
        "n": n,
        "label": "nearly-sorted (25 swapped pairs)",
        "results": {"insertion": insert_stats, "counting": counting_stats},
    })
    return {"sizes": list(sizes), "quadratic_cap": quadratic_cap, "rows": rows}


def _project_quadratic(cap: int, n: int, seed: int = 42) -> dict:
    """Measure at the cap and scale by n^2 -- honest, clearly labelled extrapolation."""
    import random
    rng = random.Random(seed)
    data = [rng.randint(0, 1000) for _ in range(cap)]
    _, stats = bubble_sort(data)
    measured = stats["time_ms"]
    return {
        "measured_at": cap,
        "measured_ms": round(measured, 3),
        "projected_ms_at_n": round(measured * (n / cap) ** 2, 1),
        "formula": f"{measured:.3f} ms * ({n}/{cap})^2",
    }


if __name__ == "__main__":
    rng = __import__("random").Random(7)
    data = [rng.randint(0, 1000) for _ in range(2000)]
    ok = sorted(data, reverse=True)
    for algo in ALGORITHMS:
        got, st = sort_scores(data, algo)
        assert got == ok, algo
        print(f"{algo:10s} n=2000 {st['time_ms']:>8.3f} ms  {st.get('comparisons')} comparisons")
    print("all four sorts agree -> OK")
