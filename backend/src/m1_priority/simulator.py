"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
simulator.py -- sensor simulator + the per-tick pipeline that ties every data
structure together.

Pipeline per tick (this is the story the demo tells):

    sensors        ->  circular queue (ingest buffer, O(1))
    25,000 plots   ->  stress score (O(1) each)
    ingest drain   ->  indexed max-heap update-key (O(log n) each)
    sliding window ->  deque trend per tracked plot (O(1) amortised)
    pump scheduler ->  extract-max over a COPY of the heap, fills 05:00-08:00
                       and 14:00-17:00 slots by priority
    counting sort  ->  orders the priority board in O(n + k)
    slot clock     ->  when a slot starts, its assigned plots are actually
                       irrigated, moisture jumps, scores collapse -- the loop closes

Threading: one daemon thread ticks every `tick_ms`.  A re-entrant lock guards
mutating operations so Flask request threads and the simulator never interleave.
`running` can be paused and `step()` advances exactly one tick (demo mode).
"""
from __future__ import annotations

import random
import threading
import time
from collections import deque

from .buffers import CircularQueue, SlidingWindowTrend
from .heap import IndexedMaxHeap
from .schema import (
    CRITICAL_MOISTURE, DEFAULT_PLOTS, MAX_PLOTS, MIN_PLOTS, SCORE_MAX,
    TICK_MINUTES, make_alert, make_plot, make_reading, status_for_score,
)
from .scheduler import PumpScheduler, current_slot_label
from .sorting import counting_sort_records
from .stress import explain, score_plot

HISTORY_SAMPLE_MOD = 12       # keep per-plot history for ~1 in 12 plots
HISTORY_POINTS = 60           # 60 ticks of history
ALERT_CAP = 250
INGEST_CAPACITY = 8192          # minimum; the real buffer scales with plot count
TREND_WINDOW = 8
HEAP_REBUILD_EVERY = 25       # periodic O(n) rebuild keeps the heap honest
DAY_START_MINUTES = 300       # 05:00 -- first tick lands at the morning window


class IrrigationSimulator:
    def __init__(self, num_plots: int = DEFAULT_PLOTS, seed: int = 42,
                 tick_ms: int = 2000) -> None:
        self.lock = threading.RLock()
        self.seed = seed
        self.rng = random.Random(seed)
        self.tick_ms = int(tick_ms)
        self.tick = 0
        self.version = 0

        # ---- controls ----------------------------------------------------
        self.drought_factor = 1.0
        self.heat_factor = 1.0
        self.power_cut = False
        self.pump_derate = 1.0
        self.plot_count = int(num_plots)

        # ---- environment --------------------------------------------------
        self.humidity = 52.0
        self.temperature = 31.0
        self.rainfall_24h = 1.0
        self.rain_ticks_left = 0
        self.clock_minutes = DAY_START_MINUTES
        self.day = 1

        # ---- data structures ---------------------------------------------
        self.heap = IndexedMaxHeap()
        self.ingest = CircularQueue(capacity=self._ingest_capacity(), overwrite_oldest=True)
        self.trend = SlidingWindowTrend(window_size=TREND_WINDOW)
        self.scheduler = PumpScheduler()

        # ---- records ------------------------------------------------------
        self.plots: dict[int, dict] = {}
        self.history: dict[int, deque] = {}
        self.alerts: deque = deque(maxlen=ALERT_CAP)
        self.alert_seq = 0
        self.schedule = {"rows": [], "slots": [], "summary": {}}
        self.irrigated_total = 0
        self.irrigated_slots: set[int] = set()
        self.pump_stats: dict[str, dict] = {}
        self.last_tick_stats: dict = {}

        self._history_mod = max(1, self.plot_count // 2000)
        self.last_ingest_batch = 0
        self._seed_plots(self.plot_count)

        # ---- background thread -------------------------------------------
        self.running = True
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _ingest_capacity(self) -> int:
        """One tick of readings must fit, so the buffer only overflows on a burst."""
        return max(INGEST_CAPACITY, int(self.plot_count * 1.25))

    # =====================================================================
    #  Seeding
    # =====================================================================
    def _seed_plots(self, n: int) -> None:
        self.plots.clear()
        self.history.clear()
        self.heap = IndexedMaxHeap()
        for pid in range(1, n + 1):
            plot = make_plot(pid, self.rng)
            score = score_plot(plot)
            self.plots[pid] = plot                 # dictionary: plot_id -> Plot record
            self.heap.insert(pid, score)
            self.trend.push(pid, score)
            if pid % self._history_mod == 0:
                self.history[pid] = deque(
                    [(0, score, plot["moisture"])], maxlen=HISTORY_POINTS)
        self._alert("info", "system", None,
                    f"Simulator initialised with {n:,} plots, "
                    f"{len(self.heap)} entries in the indexed max-heap.")
        self._rebuild_schedule()

    # =====================================================================
    #  Core tick
    # =====================================================================
    def tick_once(self, rebuild_schedule: bool = True) -> dict:
        """Advance the simulation by TICK_MINUTES of simulated time."""
        with self.lock:
            t0 = time.perf_counter()
            self.tick += 1
            self.clock_minutes += TICK_MINUTES
            if self.clock_minutes >= 1440:
                self.clock_minutes -= 1440
                self.day += 1
                self.irrigated_slots.clear()

            self._advance_weather()
            updates, critical_hits = self._advance_sensors_and_scores()
            self._advance_trends()
            self._flush_ingest()
            self._execute_current_slot()
            if rebuild_schedule or self.tick % 5 == 0:
                self._rebuild_schedule()
            if self.tick % HEAP_REBUILD_EVERY == 0:
                self._rebuild_heap()

            self.version += 1
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.last_tick_stats = {
                "tick": self.tick,
                "elapsed_ms": round(elapsed_ms, 2),
                "plots_updated": updates,
                "critical_now": critical_hits,
                "heap_size": len(self.heap),
                "queue_depth": len(self.ingest),
            }
            return self.last_tick_stats

    # ---------------------------------------------------------- weather ----
    def _advance_weather(self) -> None:
        rng = self.rng
        self.humidity = max(18.0, min(92.0, self.humidity + rng.gauss(0, 2.0)))
        base_temp = 30.0 + 3.2 * self.heat_factor
        self.temperature = max(16.0, min(46.0, self.temperature + (base_temp - self.temperature) * 0.15 + rng.gauss(0, 0.6)))
        if self.rain_ticks_left > 0:
            self.rain_ticks_left -= 1
            self.rainfall_24h += rng.uniform(2.0, 7.0)
        self.rainfall_24h = max(0.0, self.rainfall_24h * 0.90 + rng.uniform(0, 0.25))

    # ------------------------------------------------ sensors and scores ---
    def _advance_sensors_and_scores(self) -> tuple[int, int]:
        rng = self.rng
        environment_loss = (0.28 * self.drought_factor) * (1.0 + 0.05 * self.heat_factor)
        for plot in self.plots.values():
            # soil moisture: evapotranspiration loss vs rainfall gain
            loss = environment_loss * (1.15 if plot["crop"] in ("Paddy", "Sugarcane") else 1.0)
            gain = self.rainfall_24h * 0.010 * (1.3 if plot["rainfall"] > 12 else 1.0)
            plot["moisture"] = max(2.0, min(88.0, plot["moisture"] - loss + gain + rng.uniform(-0.35, 0.35)))

            # micro-climate: each plot drifts around the regional weather
            plot["temperature"] = max(14.0, min(48.0, plot["temperature"] + (self.temperature - plot["temperature"]) * 0.20 + rng.gauss(0, 0.4)))
            plot["humidity"] = max(12.0, min(96.0, plot["humidity"] + (self.humidity - plot["humidity"]) * 0.20 + rng.gauss(0, 1.2)))
            plot["rainfall"] = max(0.0, self.rainfall_24h * rng.uniform(0.8, 1.2))

            old = plot["stress_score"]
            new = score_plot(plot, drought_factor=self.drought_factor, heat_factor=self.heat_factor)
            if new != old:
                plot["score_updated_tick"] = self.tick
                self.heap.update_key(plot["plot_id"], new)     # O(log n), indexed
            plot["trend"] = self.trend.trend(plot["plot_id"])

            self.ingest.enqueue(make_reading(plot["plot_id"], self.tick, plot))

        critical = sum(1 for p in self.plots.values() if p["moisture"] < CRITICAL_MOISTURE)
        self._raise_threshold_alerts(critical)
        return len(self.plots), critical

    def _advance_trends(self) -> None:
        for pid, plot in self.plots.items():
            if pid % self._history_mod == 0 or plot["stress_score"] > 450:
                self.trend.push(pid, plot["stress_score"])
                hist = self.history.get(pid)
                if hist is None:
                    hist = self.history[pid] = deque(maxlen=HISTORY_POINTS)
                hist.append((self.tick, plot["stress_score"], round(plot["moisture"], 2)))

    def _flush_ingest(self) -> None:
        """Consume the ingest buffer in one batch -- O(k) dequeue, O(1) each."""
        batch = self.ingest.drain()
        if batch:
            self.last_ingest_batch = len(batch)

    def _rebuild_heap(self) -> None:
        fresh = IndexedMaxHeap()
        for pid, plot in self.plots.items():
            fresh.insert(pid, plot["stress_score"])
        self.heap = fresh

    # ------------------------------------------------------------ alerts ---
    def _alert(self, severity: str, kind: str, plot_id, message: str) -> None:
        self.alert_seq += 1
        self.alerts.appendleft(make_alert(
            self.alert_seq, self.tick, self.clock_label(), severity, kind, plot_id, message))

    def _raise_threshold_alerts(self, critical_now: int) -> None:
        if self.tick % 5 == 0:
            self._alert("info", "grid", None,
                        f"Tick {self.tick}: {critical_now:,} plots below the "
                        f"{CRITICAL_MOISTURE:.0f}% emergency moisture line; "
                        f"{self.scheduler.seats_per_cycle} pump seats available this cycle.")
        if self.tick % 10 == 0:
            top = self.heap.peek()
            if top:
                plot = self.plots.get(top[1], {})
                self._alert("critical", "moisture", top[1],
                            f"Plot {top[1]} ({plot.get('village', '?')}, {plot.get('crop', '?')}) "
                            f"hits top priority with score {top[0]} and "
                            f"{plot.get('moisture', 0):.1f}% moisture.")

    # --------------------------------------------------- irrigation loop ---
    def _execute_current_slot(self) -> None:
        """When the clock enters a window slot, actually run that slot's pumps."""
        slot = current_slot_label(self.clock_minutes)
        if not slot["in_window"]:
            return
        idx = slot["slot_index"]
        if idx in self.irrigated_slots:
            return
        rows = [r for r in self.schedule["rows"] if r["slot_index"] == idx]
        if not rows:
            self.irrigated_slots.add(idx)
            return
        for row in rows:
            plot = self.plots.get(row["plot_id"])
            if not plot:
                continue
            plot["moisture"] = min(84.0, plot["moisture"] + 26.0 + self.rng.uniform(0, 6))
            plot["rainfall"] = max(0.0, plot["rainfall"] - 1.0)
            plot["last_irrigated_tick"] = self.tick
            score_plot(plot, drought_factor=self.drought_factor, heat_factor=self.heat_factor)
            self.heap.update_key(plot["plot_id"], plot["stress_score"])
            stats = self.pump_stats.setdefault(row["pump_id"], {"runs": 0, "litres": 0.0})
            stats["runs"] += 1
            stats["litres"] += row["eta_litres"]
        self.irrigated_slots.add(idx)
        self.irrigated_total += len(rows)
        self._alert("info", "pump", None,
                    f"{slot['slot_label']} ({slot['window']} window): {len(rows)} plots "
                    f"irrigated across {len({r['pump_id'] for r in rows})} pumps.")

    # -------------------------------------------------------- scheduling ---
    def _rebuild_schedule(self, force: bool = False) -> None:
        for row in self.schedule.get("rows", []):
            plot = self.plots.get(row["plot_id"])
            if plot:
                plot["scheduled_slot"] = None
                plot["pump_id"] = None
        self.schedule = self.scheduler.build_schedule(
            self.plots, self.heap, tick=self.tick,
            power_cut=self.power_cut, pump_derate=self.pump_derate)
        if self.power_cut:
            self.schedule["summary"]["note"] = "Power cut active: evening window shed, pumps at half fleet."

    # =====================================================================
    #  Controls (called from the Simulation Controls panel)
    # =====================================================================
    def apply_event(self, kind: str, value=None) -> dict:
        """kind: drought | rain | power_cut | heatwave | reset | plot_count | speed | run"""
        with self.lock:
            kind = (kind or "").lower()
            if kind == "drought":
                self.drought_factor = float(value) if value is not None else min(1.6, self.drought_factor + 0.15)
                self.drought_factor = max(0.6, min(1.8, self.drought_factor))
                self._alert("warning", "environment", None,
                            f"Drought stress level set to x{self.drought_factor:.2f} "
                            f"(soil loses moisture {self.drought_factor:.2f}x faster).")
            elif kind == "rain":
                mm = float(value) if value is not None else 40.0
                self.rainfall_24h += mm
                self.rain_ticks_left = 6
                self.drought_factor = max(0.6, self.drought_factor - 0.10)
                self._alert("info", "environment", None,
                            f"Rain event: +{mm:.0f} mm in the next hour, drought level eased.")
            elif kind == "heatwave":
                self.heat_factor = min(1.8, self.heat_factor + 0.25)
                self._alert("warning", "environment", None,
                            f"Heatwave: evapotranspiration factor now x{self.heat_factor:.2f}.")
            elif kind == "power_cut":
                self.power_cut = bool(value) if value is not None else not self.power_cut
                self._alert("critical" if self.power_cut else "info", "grid", None,
                            "POWER CUT: evening window shed, half the pump fleet offline."
                            if self.power_cut else "Power restored: full pump fleet back online.")
            elif kind == "burst":
                # flood the ingest buffer with 3x readings to demonstrate the
                # overflow policy and the dropped counter
                extra = int(value) if value is not None else self.plot_count * 2
                for i in range(extra):
                    self.ingest.enqueue(("burst", self.tick, i))
                self._alert("warning", "system", None,
                            f"Sensor burst: {extra:,} extra readings pushed into a "
                            f"{self.ingest.capacity:,}-slot circular buffer; "
                            f"{self.ingest.dropped:,} dropped by the overflow policy.")
            elif kind == "reset":
                return self.reset()
            elif kind == "plot_count":
                n = int(value) if value is not None else DEFAULT_PLOTS
                return self.set_plot_count(n)
            elif kind == "speed":
                self.tick_ms = max(300, int(value or 2000))
            elif kind == "run":
                self.running = bool(value) if value is not None else not self.running
            else:
                return {"ok": False, "error": f"unknown event '{kind}'"}
            self._rebuild_schedule(force=True)
            self.version += 1
            return {"ok": True, "event": kind, "drought_factor": self.drought_factor,
                    "heat_factor": self.heat_factor, "power_cut": self.power_cut,
                    "rainfall_24h": round(self.rainfall_24h, 1)}

    def set_plot_count(self, n: int) -> dict:
        n = max(MIN_PLOTS, min(MAX_PLOTS, int(n)))
        self.plot_count = n
        self._history_mod = max(1, n // 2000)
        self._seed_plots(n)
        self.version += 1
        return {"ok": True, "plot_count": n}

    def reset(self) -> dict:
        self.rng = random.Random(self.seed)
        self.tick = 0
        self.day = 1
        self.clock_minutes = DAY_START_MINUTES
        self.drought_factor = 1.0
        self.heat_factor = 1.0
        self.power_cut = False
        self.pump_derate = 1.0
        self.humidity, self.temperature, self.rainfall_24h = 52.0, 31.0, 1.0
        self.rain_ticks_left = 0
        self.alerts.clear()
        self.alert_seq = 0
        self.irrigated_total = 0
        self.irrigated_slots.clear()
        self.pump_stats.clear()
        self.ingest = CircularQueue(capacity=self._ingest_capacity(), overwrite_oldest=True)
        self.trend = SlidingWindowTrend(window_size=TREND_WINDOW)
        self._seed_plots(self.plot_count)
        self.version += 1
        return {"ok": True, "reset": True, "plot_count": self.plot_count}

    # =====================================================================
    #  Read models (what the API returns)
    # =====================================================================
    def clock_label(self) -> str:
        m = self.clock_minutes % 1440
        return f"Day {self.day} {m // 60:02d}:{m % 60:02d}"

    def counts(self) -> dict:
        buckets = {"CRITICAL": 0, "HIGH": 0, "MODERATE": 0, "OK": 0}
        scheduled = 0
        for plot in self.plots.values():
            buckets[plot["status"]] = buckets.get(plot["status"], 0) + 1
            if plot.get("scheduled_slot") is not None:
                scheduled += 1
        return {
            "plots": len(self.plots),
            "critical": buckets["CRITICAL"],
            "high": buckets["HIGH"],
            "moderate": buckets["MODERATE"],
            "ok": buckets["OK"],
            "scheduled": scheduled,
            "irrigated_total": self.irrigated_total,
        }

    def environment(self) -> dict:
        plots = self.plots.values()
        n = max(1, len(self.plots))
        avg_m = sum(p["moisture"] for p in plots) / n
        avg_t = sum(p["temperature"] for p in plots) / n
        avg_s = sum(p["stress_score"] for p in plots) / n
        return {
            "avg_moisture": round(avg_m, 2),
            "avg_temperature": round(avg_t, 2),
            "avg_stress": round(avg_s, 1),
            "regional_humidity": round(self.humidity, 1),
            "regional_temperature": round(self.temperature, 1),
            "rainfall_24h": round(self.rainfall_24h, 2),
            "raining": self.rain_ticks_left > 0,
        }

    def top_plots(self, limit: int = 50, algorithm: str = "counting",
                  village: str | None = None, crop: str | None = None,
                  status: str | None = None) -> dict:
        """Priority board rows.  Default ordering = COUNTING SORT over the
        candidates, because scores are integers in [0,1000] -> O(n + k)."""
        t0 = time.perf_counter()
        # take a generous candidate pool from the heap copy, then sort it properly
        pool_size = min(len(self.heap), max(limit * 4, 400))
        drained = self.heap.drain(limit=pool_size, copy=True)
        rows = [self.plots[pid] for _, pid in drained if pid in self.plots]
        if village:
            rows = [r for r in rows if r["village"] == village]
        if crop:
            rows = [r for r in rows if r["crop"] == crop]
        if status:
            rows = [r for r in rows if r["status"] == status.upper()]

        records = [(r["stress_score"], r["plot_id"]) for r in rows]
        sort_ms = 0.0
        if algorithm == "counting":
            ts = time.perf_counter()
            ordered = counting_sort_records(records, max_value=SCORE_MAX)
            sort_ms = (time.perf_counter() - ts) * 1000.0
        else:
            from .sorting import sort_scores
            ts = time.perf_counter()
            ordered_scores, _ = sort_scores([s for s, _ in records], algorithm)
            by_score: dict[int, list[int]] = {}
            for s, pid in records:
                by_score.setdefault(s, []).append(pid)
            ordered = []
            for s in ordered_scores:
                ids = by_score.get(s)
                if ids:
                    ordered.append((s, ids.pop(0)))
            sort_ms = (time.perf_counter() - ts) * 1000.0

        out = []
        for rank, (score, pid) in enumerate(ordered[:limit], start=1):
            p = self.plots.get(pid)
            if not p:
                continue
            out.append({
                "rank": rank, "plot_id": pid, "village": p["village"], "crop": p["crop"],
                "stress_score": score, "status": p["status"],
                "moisture": round(p["moisture"], 1),
                "temperature": round(p["temperature"], 1),
                "humidity": round(p["humidity"], 1),
                "rainfall": round(p["rainfall"], 2),
                "trend": round(p["trend"], 1),
                "area_acres": p["area_acres"], "pump_id": p.get("pump_id"),
                "scheduled_slot": p.get("scheduled_slot"),
                "emergency": p["moisture"] < CRITICAL_MOISTURE,
                "last_irrigated_tick": p.get("last_irrigated_tick"),
            })
        return {
            "algorithm": algorithm,
            "candidates": len(rows),
            "sort_ms": round(sort_ms, 4),
            "total_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "rows": out,
        }

    def schedule_payload(self, rows_limit: int = 40, trim: bool = True) -> dict:
        """Full schedule for the timeline endpoint.

        trim=True drops fields the timeline does not render (eta, runtime, window
        key, status on assignments) -- 288 seats is a large payload to push every
        few seconds, and every dropped field is bandwidth the demo does not need.
        """
        slots = []
        for s in self.schedule.get("slots", []):
            rows = s.get("assignments", [])
            slots.append({
                "slot_index": s["slot_index"], "window": s["window"],
                "window_label": s.get("window_label"), "slot_label": s["slot_label"],
                "active_pumps": s.get("active_pumps", 0),
                "assignments": [
                    {"slot_index": r["slot_index"], "pump_id": r["pump_id"],
                     "plot_id": r["plot_id"], "stress_score": r["stress_score"],
                     "emergency": r["emergency"], "priority_rank": r["priority_rank"],
                     "reason": None if trim else r.get("reason")}
                    for r in rows
                ],
            })
        rows = []
        for r in self.schedule.get("rows", [])[:rows_limit]:
            rows.append({
                "priority_rank": r["priority_rank"], "slot_index": r["slot_index"],
                "slot_label": r["slot_label"], "window": r["window"],
                "pump_id": r["pump_id"], "plot_id": r["plot_id"],
                "village": r["village"], "crop": r["crop"],
                "stress_score": r["stress_score"], "status": r["status"],
                "emergency": r["emergency"], "reason": r.get("reason"),
                "eta_litres": r.get("eta_litres"),
            })
        return {"slots": slots, "rows": rows, "summary": self.schedule.get("summary", {})}

    def alerts_payload(self, limit: int = 60) -> list[dict]:
        return list(self.alerts)[:limit]

    def trend_payload(self, plot_id: int) -> dict:
        plot = self.plots.get(plot_id)
        if not plot:
            return {"found": False, "plot_id": plot_id}
        hist = self.history.get(plot_id)
        if hist is None:                     # not a sampled plot: show what we have
            series = self.trend.series(plot_id)
            points = [{"tick": self.tick - (len(series) - i - 1), "stress_score": s, "moisture": None}
                      for i, s in enumerate(series)]
        else:
            points = [{"tick": t, "stress_score": s, "moisture": m} for t, s, m in hist]
        return {
            "found": True, "plot_id": plot_id, "village": plot["village"], "crop": plot["crop"],
            "status": plot["status"], "stress_score": plot["stress_score"],
            "moisture": round(plot["moisture"], 1), "trend": round(plot["trend"], 1),
            "window": self.trend.series(plot_id),
            "rolling_max": self.trend.rolling_max(plot_id),
            "rolling_min": self.trend.rolling_min(plot_id),
            "mean": self.trend.mean(plot_id),
            "delta": self.trend.delta(plot_id),
            "points": points,
            "explain": explain(plot, drought_factor=self.drought_factor),
        }

    def pump_payload(self) -> list[dict]:
        out = []
        for i in range(self.scheduler.pump_count):
            pid = self.scheduler.pumps[i]
            stats = self.pump_stats.get(pid, {"runs": 0, "litres": 0.0})
            row = next((r for r in self.schedule.get("rows", []) if r["pump_id"] == pid), None)
            out.append({
                "pump_id": pid, "plots_scheduled": sum(1 for r in self.schedule.get("rows", []) if r["pump_id"] == pid),
                "runs": stats["runs"], "litres": round(stats["litres"], 1),
                "current_plot": row["plot_id"] if row else None,
                "state": "OFFLINE" if (self.power_cut and i >= max(1, self.scheduler.pump_count // 2)) else
                         ("RUNNING" if row else "IDLE"),
            })
        return out

    def state(self, schedule_rows: int = 120, alert_limit: int = 40) -> dict:
        """Compact snapshot for the 2-second poll.

        Deliberately does NOT include the 288-seat slot grid: the timeline fetches
        /schedule at a slower cadence instead.  This keeps the hot poll small.
        """
        with self.lock:
            slot = current_slot_label(self.clock_minutes)
            return {
                "meta": {
                    "module": "m1_priority", "tick": self.tick, "day": self.day,
                    "clock": self.clock_label(), "clock_minutes": self.clock_minutes % 1440,
                    "version": self.version, "running": self.running,
                    "tick_ms": self.tick_ms, "seed": self.seed,
                },
                "slot": slot,
                "counts": self.counts(),
                "environment": self.environment(),
                "controls": {
                    "drought_factor": round(self.drought_factor, 2),
                    "heat_factor": round(self.heat_factor, 2),
                    "power_cut": self.power_cut,
                    "pump_derate": self.pump_derate,
                    "plot_count": self.plot_count,
                    "tick_ms": self.tick_ms,
                    "running": self.running,
                },
                "schedule": {"summary": self.schedule.get("summary", {})},
                "pumps": self.pump_payload(),
                "alerts": self.alerts_payload(alert_limit),
                "data_structures": {
                    "heap": self.heap.stats(),
                    "circular_queue": self.ingest.stats(),
                    "deque_trend": self.trend.stats(),
                },
                "last_tick": self.last_tick_stats,
            }

    # =====================================================================
    #  Background thread
    # =====================================================================
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="m1-simulator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def is_running_thread(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.running:
                try:
                    self.tick_once()
                except Exception as exc:                    # never kill the demo thread
                    with self.lock:
                        self._alert("critical", "system", None, f"Tick error: {exc!r}")
            self._stop.wait(self.tick_ms / 1000.0)


# ---------------------------------------------------------------------------
# Module-level singleton: Flask uses this, tests can build their own
# ---------------------------------------------------------------------------
_simulator: IrrigationSimulator | None = None


def get_simulator(**kwargs) -> IrrigationSimulator:
    global _simulator
    if _simulator is None:
        _simulator = IrrigationSimulator(**kwargs)
    return _simulator


def start_simulator_thread(**kwargs) -> IrrigationSimulator:
    sim = get_simulator(**kwargs)
    sim.start()
    return sim
