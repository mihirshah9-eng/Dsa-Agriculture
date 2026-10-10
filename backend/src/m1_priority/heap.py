"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
heap.py -- the INDEXED MAX-HEAP.

Why "indexed"?
    A plain binary heap can peek the maximum in O(1) and insert in O(log n),
    but to change the priority of an element that is already inside the heap
    you must first FIND it -- O(n) with a linear scan.  Because our sensor
    simulator re-scores thousands of *already-queued* plots every tick, we keep
    a dictionary  plot_id -> heap position  (the "index").  update_key() then
    jumps straight to the element and sifts, giving O(log n) instead of O(n).

    This dictionary is exactly the point the report asks us to make:
        peek O(1)  |  insert O(log n)  |  update-key O(log n)  |  extract-max O(log n)

Ordering rule (deterministic, so demos are reproducible):
    (score, plot_id) compared as a tuple -> higher score wins; on a tie the
    higher plot_id wins.  Never rely on insertion order.
"""
from __future__ import annotations

import heapq


class IndexedMaxHeap:
    """Max-heap of (score, plot_id) with an O(1) plot_id -> index map."""

    __slots__ = ("_heap", "_pos", "ops")

    def __init__(self) -> None:
        self._heap: list[tuple[int, int]] = []   # heap[i] = (score, plot_id)
        self._pos: dict[int, int] = {}           # plot_id -> index in _heap
        self.ops = {"insert": 0, "update": 0, "extract": 0, "sift_up": 0, "sift_down": 0}

    # ------------------------------------------------------------------ basics
    def __len__(self) -> int:
        return len(self._heap)

    def __contains__(self, plot_id: int) -> bool:
        return plot_id in self._pos

    @property
    def is_empty(self) -> bool:
        return not self._heap

    def peek(self) -> tuple[int, int] | None:
        """O(1) read of (score, plot_id) of the most water-stressed plot."""
        return self._heap[0] if self._heap else None

    def score_of(self, plot_id: int) -> int | None:
        idx = self._pos.get(plot_id)
        return self._heap[idx][0] if idx is not None else None

    # ------------------------------------------------------------------ sifts
    @staticmethod
    def _parent(i: int) -> int:
        return (i - 1) >> 1

    @staticmethod
    def _left(i: int) -> int:
        return (i << 1) + 1

    def _swap(self, i: int, j: int) -> None:
        heap, pos = self._heap, self._pos
        heap[i], heap[j] = heap[j], heap[i]
        pos[heap[i][1]] = i
        pos[heap[j][1]] = j

    def _sift_up(self, i: int) -> None:
        self.ops["sift_up"] += 1
        heap = self._heap
        while i > 0:
            parent = self._parent(i)
            if heap[i] > heap[parent]:          # tuple compare = (score, plot_id)
                self._swap(i, parent)
                i = parent
            else:
                break

    def _sift_down(self, i: int) -> None:
        self.ops["sift_down"] += 1
        heap, n = self._heap, len(self._heap)
        while True:
            left, right, largest = self._left(i), self._left(i) + 1, i
            if left < n and heap[left] > heap[largest]:
                largest = left
            if right < n and heap[right] > heap[largest]:
                largest = right
            if largest == i:
                return
            self._swap(i, largest)
            i = largest

    # --------------------------------------------------------------- mutators
    def insert(self, plot_id: int, score: int) -> None:
        """O(log n).  Re-inserting a present plot_id is treated as update_key."""
        if plot_id in self._pos:
            self.update_key(plot_id, score)
            return
        self.ops["insert"] += 1
        self._heap.append((int(score), int(plot_id)))
        self._pos[plot_id] = len(self._heap) - 1
        self._sift_up(len(self._heap) - 1)

    def update_key(self, plot_id: int, new_score: int) -> None:
        """O(log n) because the index dictionary already locates the element."""
        idx = self._pos.get(plot_id)
        if idx is None:
            self.insert(plot_id, new_score)
            return
        self.ops["update"] += 1
        old = self._heap[idx][0]
        new_score = int(new_score)
        if new_score == old:
            return
        self._heap[idx] = (new_score, plot_id)
        if new_score > old:
            self._sift_up(idx)
        else:
            self._sift_down(idx)

    def remove(self, plot_id: int) -> bool:
        """O(log n) delete of an arbitrary element (used when a plot is retired)."""
        idx = self._pos.get(plot_id)
        if idx is None:
            return False
        last = len(self._heap) - 1
        if idx != last:
            self._swap(idx, last)
        self._heap.pop()
        self._pos.pop(plot_id, None)
        if idx < len(self._heap):
            self._sift_down(idx)
            self._sift_up(idx)
        return True

    def extract_max(self) -> tuple[int, int] | None:
        """O(log n) pop of the highest-priority plot."""
        if not self._heap:
            return None
        self.ops["extract"] += 1
        top = self._heap[0]
        last = len(self._heap) - 1
        if last:
            self._swap(0, last)
        self._heap.pop()
        self._pos.pop(top[1], None)
        if self._heap:
            self._sift_down(0)
        return top

    # ---------------------------------------------------------------- readers
    def snapshot(self, limit: int | None = None) -> list[tuple[int, int]]:
        """Heap-array order, NOT sorted order (cheap: O(n) / O(limit))."""
        return self._heap if limit is None else self._heap[:limit]

    def top_k(self, k: int) -> list[tuple[int, int]]:
        """Sorted top-k in O(n log k) using a small auxiliary MIN-heap.

        The main heap is left untouched -- the Priority Board uses this so that
        polling the UI never disturbs the scheduler's data structure.
        """
        if k >= len(self._heap):
            return self.drain(limit=None, copy=True)
        small: list[tuple[int, int]] = []
        for item in self._heap:
            if len(small) < k:
                heapq.heappush(small, item)
            elif item > small[0]:
                heapq.heapreplace(small, item)
        return sorted(small, reverse=True)

    def drain(self, limit: int | None = None, copy: bool = True) -> list[tuple[int, int]]:
        """Extract-max until empty (or `limit` items).  Returns DESCENDING order.

        Used by the Pump Scheduler.  With copy=True the real heap is untouched,
        so the same tick can be re-scheduled without rebuilding.
        """
        if copy:
            work = IndexedMaxHeap()
            work._heap = list(self._heap)
            work._pos = {pid: i for i, (_, pid) in enumerate(work._heap)}
        else:
            work = self
        out: list[tuple[int, int]] = []
        while work._heap and (limit is None or len(out) < limit):
            item = work.extract_max()
            if item is None:
                break
            out.append(item)
        return out

    # ------------------------------------------------------------ integrity
    def validate(self) -> bool:
        """Debug helper: heap property + index dictionary agree.  O(n)."""
        heap, pos = self._heap, self._pos
        if len(pos) != len(heap):
            return False
        for i in range(len(heap)):
            if pos.get(heap[i][1]) != i:
                return False
            left, right = self._left(i), self._left(i) + 1
            if left < len(heap) and heap[left] > heap[i]:
                return False
            if right < len(heap) and heap[right] > heap[i]:
                return False
        return True

    def depth(self) -> int:
        """Height of the binary heap -> useful in the viva ('log2 n vs measured')."""
        n, d = len(self._heap), 0
        while n > 1:
            n = (n + 1) >> 1
            d += 1
        return d

    def stats(self) -> dict:
        return {
            "size": len(self._heap),
            "depth": self.depth(),
            "top": self.peek(),
            "ops": dict(self.ops),
        }


# ---------------------------------------------------------------------------
# Plain heap sort (array in, array out) -- used by sorting.py benchmarks
# ---------------------------------------------------------------------------
def heap_sort(values: list[int], descending: bool = False) -> list[int]:
    """In-place binary max-heap sort.  Time O(n log n), space O(1)."""
    arr = list(values)
    n = len(arr)

    def sift(i: int, size: int) -> None:
        while True:
            left, right, big = 2 * i + 1, 2 * i + 2, i
            if left < size and arr[left] > arr[big]:
                big = left
            if right < size and arr[right] > arr[big]:
                big = right
            if big == i:
                return
            arr[i], arr[big] = arr[big], arr[i]
            i = big

    for i in range(n // 2 - 1, -1, -1):          # build-heap, O(n)
        sift(i, n)
    for end in range(n - 1, 0, -1):              # n extractions, O(n log n)
        arr[0], arr[end] = arr[end], arr[0]
        sift(0, end)
    return arr if descending is False else list(reversed(arr))


def heap_sort_desc_records(records: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Heap-sort (score, plot_id) records into DESCENDING priority order.

    Sorting the tuple itself (not just the score) keeps the tie-break rule
    identical to the heap's, so the scheduler and the sorter never disagree.
    """
    arr = sorted(records)                       # ascending by (score, plot_id)
    n = len(arr)

    def sift(i: int, size: int) -> None:
        while True:
            left, right, big = 2 * i + 1, 2 * i + 2, i
            if left < size and arr[left] > arr[big]:
                big = left
            if right < size and arr[right] > arr[big]:
                big = right
            if big == i:
                break
            arr[i], arr[big] = arr[big], arr[i]
            i = big

    for i in range(n // 2 - 1, -1, -1):
        sift(i, n)
    for end in range(n - 1, 0, -1):
        arr[0], arr[end] = arr[end], arr[0]
        sift(0, end)
    return arr[::-1]
