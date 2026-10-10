"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
buffers.py -- Circular Queue (ingest buffer) and Deque (sliding-window trend).

1) CircularQueue
   The sensor simulator produces readings faster than the scoring pipeline
   consumes them.  A fixed-size ring buffer absorbs the burst with O(1) enqueue
   and O(1) dequeue and *zero* reallocation.  When the ring is full we apply an
   explicit overflow policy and count the drops, because a silently growing
   list is exactly the failure mode this data structure exists to prevent.
   Time: enqueue O(1), dequeue O(1), space O(capacity).

2) SlidingWindowTrend (collections.deque)
   Stress is a trend, not a snapshot: a plot that jumped 40 points in 20 minutes
   outranks a plot that has been statically dry.  We keep the last N scores per
   watched plot in a bounded deque (O(1) append, O(1) popleft, O(1) length) and
   additionally maintain a MONOTONIC deque to answer "rolling maximum in O(1)
   amortised" instead of scanning the window in O(n).
"""
from __future__ import annotations

from collections import deque


class CircularQueue:
    """Fixed-capacity ring buffer of readings (FIFO) with overflow accounting."""

    __slots__ = ("capacity", "_buf", "_head", "_tail", "_size", "overwrite_oldest",
                 "pushed", "popped", "dropped", "high_water", "overwrites")

    def __init__(self, capacity: int = 4096, overwrite_oldest: bool = True) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = int(capacity)
        self._buf: list = [None] * self.capacity
        self._head = 0            # next slot to read
        self._tail = 0            # next slot to write
        self._size = 0
        self.overwrite_oldest = bool(overwrite_oldest)   # False -> drop newest
        self.pushed = 0
        self.popped = 0
        self.dropped = 0
        self.high_water = 0
        self.overwrites = 0

    # ------------------------------------------------------------- primitives
    def is_empty(self) -> bool:
        return self._size == 0

    def is_full(self) -> bool:
        return self._size == self.capacity

    def __len__(self) -> int:
        return self._size

    def clear(self) -> None:
        self._buf = [None] * self.capacity
        self._head = self._tail = self._size = 0

    # ------------------------------------------------------------------ queue
    def enqueue(self, item) -> bool:
        """O(1).  Returns True if the item was stored, False if it was dropped."""
        self.pushed += 1
        if self._size == self.capacity:
            if not self.overwrite_oldest:
                self.dropped += 1
                return False
            # ring is full: advance the read head, overwriting the oldest slot
            self._buf[self._tail] = item
            self._tail = (self._tail + 1) % self.capacity
            self._head = self._tail
            self.dropped += 1
            self.overwrites += 1
            return False
        self._buf[self._tail] = item
        self._tail = (self._tail + 1) % self.capacity
        self._size += 1
        if self._size > self.high_water:
            self.high_water = self._size
        return True

    def dequeue(self):
        """O(1).  Returns the oldest item or None when empty."""
        if self._size == 0:
            return None
        item = self._buf[self._head]
        self._buf[self._head] = None
        self._head = (self._head + 1) % self.capacity
        self._size -= 1
        self.popped += 1
        return item

    def drain(self, max_items: int | None = None) -> list:
        """Dequeue everything (or up to max_items) as one batch -- O(k)."""
        out = []
        while self._size and (max_items is None or len(out) < max_items):
            out.append(self.dequeue())
        return out

    def peek(self):
        return self._buf[self._head] if self._size else None

    def stats(self) -> dict:
        return {
            "capacity": self.capacity,
            "size": self._size,
            "utilization": round(self._size / self.capacity, 4),
            "high_water": self.high_water,
            "pushed": self.pushed,
            "popped": self.popped,
            "dropped": self.dropped,
            "overwrites": self.overwrites,
        }


class SlidingWindowTrend:
    """Bounded deque of per-plot stress scores + O(1) rolling max / min / delta.

    shape: plot_id -> {
        "window": deque(maxlen=N) of scores,
        "values": {score: count}  (for O(1) amortised mean),
        "trend": last - first,
        "max": rolling maximum (monotonic deque),
        "min": rolling minimum,
    }
    """

    __slots__ = ("window_size", "_data", "_mono_max", "_mono_min", "_tick")

    def __init__(self, window_size: int = 6) -> None:
        self.window_size = int(window_size)
        self._data: dict[int, deque] = {}
        self._mono_max: dict[int, deque] = {}   # indices of decreasing values
        self._mono_min: dict[int, deque] = {}   # indices of increasing values
        self._tick: dict[int, int] = {}

    def push(self, plot_id: int, score: int) -> None:
        """O(1) amortised."""
        dq = self._data.get(plot_id)
        if dq is None:
            dq = deque(maxlen=self.window_size)
            self._data[plot_id] = dq
            self._mono_max[plot_id] = deque()
            self._mono_min[plot_id] = deque()
            self._tick[plot_id] = 0
        t = self._tick[plot_id] = self._tick[plot_id] + 1
        dq.append(score)

        mx, mn = self._mono_max[plot_id], self._mono_min[plot_id]
        while mx and mx[-1][1] <= score:
            mx.pop()
        mx.append((t, score))
        while mn and mn[-1][1] >= score:
            mn.pop()
        mn.append((t, score))

        # evict entries that fell out of the fixed-size window
        cutoff = t - self.window_size
        while mx and mx[0][0] <= cutoff:
            mx.popleft()
        while mn and mn[0][0] <= cutoff:
            mn.popleft()

    def series(self, plot_id: int) -> list[int]:
        dq = self._data.get(plot_id)
        return list(dq) if dq else []

    def trend(self, plot_id: int) -> float:
        """Positive = getting drier/stressed faster."""
        series = self.series(plot_id)
        if len(series) < 2:
            return 0.0
        return round((series[-1] - series[0]) / (len(series) - 1), 2)

    def delta(self, plot_id: int) -> int:
        series = self.series(plot_id)
        return (series[-1] - series[0]) if len(series) >= 2 else 0

    def rolling_max(self, plot_id: int) -> int | None:
        """O(1) amortised thanks to the monotonic deque."""
        mx = self._mono_max.get(plot_id)
        return mx[0][1] if mx else None

    def rolling_min(self, plot_id: int) -> int | None:
        mn = self._mono_min.get(plot_id)
        return mn[0][1] if mn else None

    def mean(self, plot_id: int) -> float:
        series = self.series(plot_id)
        return round(sum(series) / len(series), 1) if series else 0.0

    def forget(self, plot_id: int) -> None:
        self._data.pop(plot_id, None)
        self._mono_max.pop(plot_id, None)
        self._mono_min.pop(plot_id, None)
        self._tick.pop(plot_id, None)

    def __len__(self) -> int:
        return len(self._data)

    def stats(self) -> dict:
        return {"tracked_plots": len(self._data), "window_size": self.window_size}


if __name__ == "__main__":  # tiny smoke test
    q = CircularQueue(capacity=4)
    for i in range(6):
        q.enqueue(i)
    assert len(q) == 4 and q.dropped == 2
    assert q.drain() == [2, 3, 4, 5]
    print("CircularQueue OK", q.stats())

    t = SlidingWindowTrend(window_size=3)
    for s in (10, 40, 25, 60):
        t.push(1, s)
    assert t.series(1) == [40, 25, 60]
    assert t.rolling_max(1) == 60 and t.rolling_min(1) == 25
    print("SlidingWindowTrend OK", t.stats(), "trend:", t.trend(1))
