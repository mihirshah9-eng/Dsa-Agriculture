"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
routes.py -- Flask blueprint `m1_bp`.

Registered in the root app.py exactly as the repo skeleton expects:

    from src.m1_priority.routes import m1_bp
    app.register_blueprint(m1_bp, url_prefix='/api/priority')

All paths below are therefore RELATIVE:
    GET  /state              -> /api/priority/state
    GET  /plots?limit=100    -> /api/priority/plots
    GET  /plots/<plot_id>    -> /api/priority/plots/42
    GET  /schedule           -> /api/priority/schedule
    GET  /alerts             -> /api/priority/alerts
    GET  /trend/<plot_id>    -> /api/priority/trend/42
    GET  /structures         -> /api/priority/structures
    GET  /benchmarks         -> /api/priority/benchmarks
    GET  /health             -> /api/priority/health
    POST /control            -> {"event": "drought"|"rain"|"power_cut"|"heatwave"|"reset", "value": ...}
    POST /step               -> advance one simulated tick
    POST /plot-count         -> {"plot_count": 25000}
"""
from __future__ import annotations

import os
import threading
import time

from flask import Blueprint, jsonify, request

from . import benchmarks as bench
from .schema import MAX_PLOTS, MIN_PLOTS, PUMP_COUNT, SCORE_MAX, WINDOWS
from .simulator import get_simulator, start_simulator_thread

m1_bp = Blueprint("m1_priority", __name__)

# ---------------------------------------------------------------------------
# Simulator lifecycle.  Started lazily on first request so that `flask run`
# with the reloader cannot spawn two simulators (WERKZEUG_RUN_MAIN guard).
# ---------------------------------------------------------------------------
_sim_lock = threading.Lock()
_bench_cache: dict = {"key": None, "payload": None, "generated_ms": None}


def _sim():
    sim = get_simulator()
    with _sim_lock:
        if not sim.is_running_thread():
            sim.start()
    return sim


def _int_param(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Health / metadata
# ---------------------------------------------------------------------------
@m1_bp.get("/health")
def health():
    sim = _sim()
    return jsonify({
        "status": "online",
        "module": "m1_priority",
        "owner": "Member 1 - Priority and Scheduling Engine",
        "tick": sim.tick,
        "plots": len(sim.plots),
        "heap_size": len(sim.heap),
        "structures": ["Indexed Max-Heap", "Circular Queue", "Deque", "Dictionary",
                       "Counting sort", "Bubble sort", "Insertion sort", "Heap sort"],
    })


@m1_bp.get("/schema")
def schema_info():
    return jsonify({
        "plot_fields": ["plot_id", "farmer_id", "village", "crop", "area_acres", "x", "y",
                        "ndvi", "water_source", "moisture", "temperature", "humidity",
                        "rainfall", "stress_score", "status", "trend", "pump_id",
                        "last_irrigated_tick", "score_updated_tick"],
        "reading_fields": ["plot_id", "tick", "timestamp", "moisture", "temperature",
                           "humidity", "rainfall"],
        "schedule_fields": ["slot_index", "window", "slot_label", "pump_id", "plot_id",
                            "village", "crop", "priority_rank", "stress_score", "status",
                            "runtime_minutes", "eta_litres", "reason"],
        "score": {"range": [0, SCORE_MAX], "bands": {"CRITICAL": ">=700", "HIGH": ">=450",
                                                     "MODERATE": ">=250", "OK": "<250"}},
        "windows": WINDOWS,
        "limits": {"plots": [MIN_PLOTS, MAX_PLOTS], "pumps": PUMP_COUNT},
    })


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------
@m1_bp.get("/state")
def state():
    """Hot poll: counts, environment, heap/queue/deque vitals, alerts, summary.

    The 288-seat slot grid is deliberately NOT here -- the timeline asks for
    /schedule on its own slower cadence.
    """
    sim = _sim()
    return jsonify(sim.state(alert_limit=_int_param("alerts", 40, 0, 250)))


@m1_bp.get("/plots")
def plots():
    sim = _sim()
    return jsonify(sim.top_plots(
        limit=_int_param("limit", 60, 1, 500),
        algorithm=request.args.get("algorithm", "counting"),
        village=request.args.get("village"),
        crop=request.args.get("crop"),
        status=request.args.get("status"),
    ))


@m1_bp.get("/plots/<int:plot_id>")
def plot_detail(plot_id: int):
    sim = _sim()
    payload = sim.trend_payload(plot_id)
    if not payload.get("found"):
        return jsonify({"error": f"plot {plot_id} not found"}), 404
    return jsonify(payload)


@m1_bp.get("/schedule")
def schedule():
    """Full 12-slot grid for the Pump Scheduler timeline.  ?full=1 adds reasons."""
    sim = _sim()
    return jsonify(sim.schedule_payload(
        rows_limit=_int_param("limit", 40, 1, 500),
        trim=request.args.get("full") != "1",
    ))


@m1_bp.get("/pumps")
def pumps():
    return jsonify({"pumps": _sim().pump_payload()})


@m1_bp.get("/alerts")
def alerts():
    return jsonify({"alerts": _sim().alerts_payload(_int_param("limit", 60, 1, 250))})


@m1_bp.get("/trend/<int:plot_id>")
def trend(plot_id: int):
    sim = _sim()
    payload = sim.trend_payload(plot_id)
    if not payload.get("found"):
        return jsonify({"error": f"plot {plot_id} not found"}), 404
    return jsonify(payload)


@m1_bp.get("/structures")
def structures():
    sim = _sim()
    return jsonify({
        "heap": sim.heap.stats(),
        "circular_queue": sim.ingest.stats(),
        "deque_trend": sim.trend.stats(),
        "dictionary": {"plot_records": len(sim.plots),
                       "history_series": len(sim.history),
                       "last_ingest_batch": getattr(sim, "last_ingest_batch", 0)},
        "last_tick": sim.last_tick_stats,
    })


# ---------------------------------------------------------------------------
# Benchmarks (cached -- a full run costs a few seconds)
# ---------------------------------------------------------------------------
@m1_bp.get("/benchmarks")
def benchmarks():
    sim = _sim()
    sizes = tuple(sorted({1_000, 5_000, 10_000, sim.plot_count}))
    key = (sizes, sim.plot_count)
    if _bench_cache["key"] == key and _bench_cache["payload"] is not None:
        payload = dict(_bench_cache["payload"])
        payload["cached"] = True
        payload["generated_ago_seconds"] = round(time.time() - _bench_cache["generated_ms"], 1)
        payload["generated_at_tick"] = sim.tick
        return jsonify(payload)

    payload = bench.run_all(scheduler=sim.scheduler, plots=sim.plots, heap=sim.heap,
                            sim=sim, sizes=sizes, seed=sim.seed)
    payload["cached"] = False
    payload["generated_at_tick"] = sim.tick
    _bench_cache.update({"key": key, "payload": payload, "generated_ms": time.time()})
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
@m1_bp.post("/control")
def control():
    sim = _sim()
    body = request.get_json(silent=True) or {}
    event = body.get("event") or request.args.get("event")
    value = body.get("value", request.args.get("value"))
    if not event:
        return jsonify({"ok": False, "error": "body must contain {\"event\": ...}"}), 400
    result = sim.apply_event(event, value)
    return jsonify(result), (200 if result.get("ok") else 400)


@m1_bp.post("/step")
def step():
    """Advance exactly one tick -- the demo 'Step' button."""
    sim = _sim()
    body = request.get_json(silent=True) or {}
    count = int(body.get("count", 1))
    count = max(1, min(60, count))
    stats = {}
    for _ in range(count):
        stats = sim.tick_once()
    return jsonify({"ok": True, "count": count, "last_tick": stats,
                    "tick": sim.tick, "clock": sim.clock_label()})


@m1_bp.post("/plot-count")
def plot_count():
    sim = _sim()
    body = request.get_json(silent=True) or {}
    n = body.get("plot_count")
    if n is None:
        return jsonify({"ok": False, "error": "body must contain {\"plot_count\": n}"}), 400
    return jsonify(sim.set_plot_count(int(n)))


@m1_bp.post("/sort-compare")
def sort_compare():
    """Side-by-side timing of the four sorts on the CURRENT live scores."""
    sim = _sim()
    body = request.get_json(silent=True) or {}
    algo = body.get("algorithm", "all")
    scores = [p["stress_score"] for p in sim.plots.values()]
    from .sorting import sort_scores

    out = {"plots": len(scores)}
    if algo == "all":
        for name in ("counting", "heap", "insertion", "bubble"):
            if name in ("bubble", "insertion") and len(scores) > 8_000:
                out[name] = {"skipped": True, "reason": "O(n^2) skipped on the live 25k set"}
                continue
            _, stats = sort_scores(scores, name)
            out[name] = stats
    else:
        _, stats = sort_scores(scores, algo)
        out[algo] = stats
    return jsonify(out)
