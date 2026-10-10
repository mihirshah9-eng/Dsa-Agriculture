"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
=====================================================

Package layout
--------------
    schema.py       shared JSON contract (Plot / Reading / Schedule) + constants
    heap.py         IndexedMaxHeap (O(1) peek, O(log n) insert/update/extract) + heap sort
    buffers.py      CircularQueue (ingest) and SlidingWindowTrend (monotonic deque)
    sorting.py      counting / bubble / insertion / heap sort + benchmark harness
    stress.py       water-stress score model and explanation breakdown
    scheduler.py    pump scheduler that fills the 05:00-08:00 and 14:00-17:00 windows
    simulator.py    25,000-plot sensor simulator + the per-tick pipeline
    benchmarks.py   measured timings + complexity table for the report
    routes.py       Flask blueprint `m1_bp`

Plug into the root app.py:

    from src.m1_priority.routes import m1_bp
    app.register_blueprint(m1_bp, url_prefix='/api/priority')
"""
from .heap import IndexedMaxHeap, heap_sort
from .buffers import CircularQueue, SlidingWindowTrend
from .scheduler import PumpScheduler
from .simulator import IrrigationSimulator, get_simulator, start_simulator_thread
from .stress import water_stress_score, score_plot, explain
from .schema import MAX_PLOTS, DEFAULT_PLOTS, PUMP_COUNT, WINDOWS

__all__ = [
    "IndexedMaxHeap", "heap_sort",
    "CircularQueue", "SlidingWindowTrend",
    "PumpScheduler",
    "IrrigationSimulator", "get_simulator", "start_simulator_thread",
    "water_stress_score", "score_plot", "explain",
    "MAX_PLOTS", "DEFAULT_PLOTS", "PUMP_COUNT", "WINDOWS",
]

__version__ = "1.0.0"
__member__ = "Member 1 - Priority and Scheduling Engine"
