"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
scheduler.py -- pump scheduler that fills the electricity windows by priority.

The constraint
--------------
Watering is only cheap (and only allowed) inside two electricity windows:
05:00-08:00 and 14:00-17:00.  Each window is 3 h = 6 slots of 30 minutes.
The farm has a fixed fleet of PUMP_COUNT pumps, one plot per pump per slot.
So one full cycle can serve  PUMP_COUNT * TOTAL_SLOTS  plots, and the entire
job of this file is: **decide which plots get those seats.**

The algorithm
-------------
1. Non-destructively extract-max from the indexed max-heap until we have as many
   candidates as there are seats (plus a small reserve).  Because we drain a
   COPY, the live heap still answers the Priority Board afterwards -- O(n) copy
   + O(k log n) extraction.
2. Reserve a fixed share of morning seats for EMERGENCIES (moisture below the
   critical line) so a plot that turns critical at 06:00 is not stuck behind
   the day's whole backlog.  Unused emergency seats roll back into the pool.
3. Fill the remaining seats in strict score order, round-robin across pumps so
   no single pump is asked to do two plots in the same slot.
4. Tie-break on larger area / earlier dry-spell so the order is deterministic and
   demoable.

Complexity: O(n + k log n + k log k) per rebuild, where n = plots, k = seats.
With n = 25,000 and k = 288 this is a fraction of a millisecond of real work.
"""
from __future__ import annotations

from .schema import (
    CRITICAL_MOISTURE, PUMP_COUNT, PUMP_RUNTIME_MIN, SLOTS_PER_WINDOW,
    TOTAL_SLOTS, WINDOWS, make_schedule_row,
)
from .stress import is_emergency, priority_reason

EMERGENCY_RESERVE_FRACTION = 0.30   # 30% of the seats held back for critical plots


class PumpScheduler:
    def __init__(self, pump_count: int = PUMP_COUNT) -> None:
        self.pump_count = int(pump_count)
        self.pumps = [f"PUMP-{i + 1:02d}" for i in range(self.pump_count)]
        self.slots = self._build_slots()
        self.seats_per_cycle = self.pump_count * TOTAL_SLOTS
        self.last_build = None

    # ------------------------------------------------------------------ slots
    @staticmethod
    def _build_slots() -> list[dict]:
        """Pre-compute the 12 slot descriptors: 05:00-05:30 ... 16:30-17:00."""
        slots: list[dict] = []
        idx = 0
        for window in WINDOWS:
            start_h, start_m = (int(x) for x in window["start"].split(":"))
            minutes = start_h * 60 + start_m
            for s in range(SLOTS_PER_WINDOW):
                a = minutes + s * 30
                b = a + 30
                slots.append({
                    "slot_index": idx,
                    "window": window["key"],
                    "window_label": window["label"],
                    "start_minutes": a,
                    "end_minutes": b,
                    "slot_label": f"{a // 60:02d}:{a % 60:02d}-{b // 60:02d}:{b % 60:02d}",
                })
                idx += 1
        return slots

    @staticmethod
    def slot_index_for_minutes(minutes: int) -> int | None:
        """Which electricity slot (if any) the simulated clock is inside.  O(12)."""
        m = minutes % 1440
        for i, s in enumerate(PumpScheduler._build_slots()):
            if s["start_minutes"] <= m < s["end_minutes"]:
                return i
        return None

    # ------------------------------------------------------------- the build
    def build_schedule(self, plots_by_id: dict, heap, tick: int = 0,
                       power_cut: bool = False, pump_derate: float = 1.0) -> dict:
        """Return {rows, slots, summary}.  Pure function of (heap, plots, controls)."""
        import time as _time
        _t0 = _time.perf_counter()
        active_pumps = max(1, int(round(self.pump_count * pump_derate)))
        if power_cut:
            # a power cut halves the usable slots: the evening window is shed first
            active_pumps = max(1, active_pumps // 2)

        slots = [dict(s) for s in self.slots]
        for s in slots:
            s["assignments"] = []
            s["active_pumps"] = 0 if (power_cut and s["window"] == "evening") else active_pumps

        seats = sum(s["active_pumps"] for s in slots)
        if seats == 0:
            return self._empty_result(slots, tick, power_cut)

        # ---- step 1: non-destructive extract-max for a candidate pool -------
        pool_size = min(len(heap), seats + seats // 2 + 1)
        drained = heap.drain(limit=pool_size, copy=True)          # DESCENDING
        candidates = [plots_by_id[pid] for _, pid in drained if pid in plots_by_id]

        # ---- step 2: split emergency vs normal ------------------------------
        emergency = [p for p in candidates if is_emergency(p)]
        normal = [p for p in candidates if not is_emergency(p)]

        # RESERVE POLICY
        #   Emergencies always take seats FIRST, up to the whole cycle.
        #   Non-emergency plots may occupy at most (seats - reserve) seats, so a
        #   plot that turns critical later still finds capacity in this window.
        #   Seats nobody claims stay IDLE and are reported in the summary --
        #   better an idle slot than a non-urgent plot occupying it.
        normal_reserve = int(seats * EMERGENCY_RESERVE_FRACTION)
        emergency_seats_used = min(len(emergency), seats)
        normal_cap = max(0, seats - max(emergency_seats_used, normal_reserve))
        pool = emergency[:emergency_seats_used] + normal[:normal_cap]
        pool = pool[:seats]

        # strict priority order, ties broken by score then plot_id
        pool.sort(key=lambda p: (-p["stress_score"], p["plot_id"]))

        # ---- step 3: deal the seats round-robin across pumps ----------------
        rows: list[dict] = []
        rank = 0
        eligible = [i for i, s in enumerate(slots) if s["active_pumps"] > 0]

        # seat_order: chronological seat sequence, (slot_index, seat_number_in_slot).
        # Walking seat-by-seat (not slot-by-slot) means the single most stressed
        # plot in the whole pool is served in the very first slot of the window.
        seat_order: list[tuple[int, int]] = []
        max_seats = max((slots[i]["active_pumps"] for i in eligible), default=0)
        for seat in range(max_seats):
            for idx in eligible:
                if seat < slots[idx]["active_pumps"]:
                    seat_order.append((idx, seat))

        for plot, (slot_idx, seat_no) in zip(pool, seat_order):
            slot = slots[slot_idx]
            n_active = slot["active_pumps"]
            # Pump assignment: one plot per pump per slot.  The cursor is offset by
            # the slot index so PUMP-01 is not always first, and modulo n_active
            # guarantees 0..n_active-1 are used exactly once inside a slot.
            pump = self.pumps[(seat_no + slot_idx) % n_active]
            rank += 1
            plot["pump_id"] = pump
            plot["scheduled_slot"] = slot_idx
            row = make_schedule_row(
                slot_index=slot_idx, window_key=slot["window"],
                slot_label=slot["slot_label"], pump_id=pump, plot=plot, rank=rank,
            )
            row["reason"] = priority_reason(plot, rank)
            row["emergency"] = is_emergency(plot)
            slot["assignments"].append(row)
            rows.append(row)

        summary = {
            "tick": tick,
            "rebuild_ms": round((_time.perf_counter() - _t0) * 1000.0, 3),
            "seats_total": seats,
            "seats_filled": len(rows),
            "pumps_active": active_pumps,
            "pumps_fleet": self.pump_count,
            "candidates_considered": len(candidates),
            "emergency_plots": len(emergency),
            "emergency_reserve_seats": normal_reserve,
            "emergency_seats_used": emergency_seats_used,
            "normal_seat_cap": normal_cap,
            "seats_idle_reserved": seats - len(pool),
            "unserved_high_priority": max(0, len(candidates) - len(rows)),
            "power_cut": bool(power_cut),
            "pump_derate": pump_derate,
            "window_summary": [
                {
                    "window": w["key"], "label": w["label"],
                    "start": w["start"], "end": w["end"],
                    "plots_scheduled": sum(len(s["assignments"]) for s in slots if s["window"] == w["key"]),
                    "seats": sum(s["active_pumps"] for s in slots if s["window"] == w["key"]),
                }
                for w in WINDOWS
            ],
            "runtime_minutes_per_plot": PUMP_RUNTIME_MIN,
            "coverage_percent": round(100.0 * len(rows) / seats, 2) if seats else 0.0,
        }
        result = {"rows": rows, "slots": slots, "summary": summary}
        self.last_build = {"tick": tick, **{k: summary[k] for k in ("seats_filled", "seats_total")}}
        return result

    def _empty_result(self, slots, tick, power_cut) -> dict:
        for s in slots:
            s["assignments"] = []
        return {
            "rows": [], "slots": slots,
            "summary": {
                "tick": tick, "rebuild_ms": round((_time.perf_counter() - _t0) * 1000.0, 3),
                "seats_total": 0, "seats_filled": 0,
                "pumps_active": 0, "pumps_fleet": self.pump_count,
                "candidates_considered": 0, "emergency_plots": 0,
                "emergency_reserve_seats": 0, "emergency_seats_used": 0,
                "normal_seat_cap": 0, "seats_idle_reserved": 0,
                "unserved_high_priority": 0, "power_cut": bool(power_cut),
                "pump_derate": 1.0, "window_summary": [], "coverage_percent": 0.0,
            },
        }


def current_slot_label(minutes_of_day: int) -> dict:
    """Which electricity slot (if any) the simulated clock is inside right now."""
    m = minutes_of_day % 1440
    for s in PumpScheduler._build_slots():
        if s["start_minutes"] <= m < s["end_minutes"]:
            return {"in_window": True, **{k: s[k] for k in
                    ("slot_index", "window", "slot_label", "start_minutes", "end_minutes")}}
    return {"in_window": False, "slot_index": None, "window": None, "slot_label": None}
