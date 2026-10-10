"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
schema.py -- shared data contract (Plot / Reading / Schedule) + simulation constants.

This is the file that encodes the Day-1 agreement between the three members.
Members 2 and 3 code against these exact field names.
"""
from __future__ import annotations

import random

# ----------------------------------------------------------------------------
# Fleet / simulation limits
# ----------------------------------------------------------------------------
MAX_PLOTS = 50_000
DEFAULT_PLOTS = 25_000
MIN_PLOTS = 500

# Stress score is an INTEGER in [0, 1000] so that COUNTING SORT is applicable.
SCORE_MIN = 0
SCORE_MAX = 1000

# ----------------------------------------------------------------------------
# Electricity windows (the constraint the scheduler fills)
# ----------------------------------------------------------------------------
# Each window is split into 30-minute slots.  3 h -> 6 slots per window.
SLOT_MINUTES = 30
WINDOWS = (
    {"key": "morning", "label": "Morning window", "start": "05:00", "end": "08:00"},
    {"key": "evening", "label": "Evening window", "start": "14:00", "end": "17:00"},
)
SLOTS_PER_WINDOW = 6            # 3 hours / 30 minutes
TOTAL_SLOTS = len(WINDOWS) * SLOTS_PER_WINDOW   # 12

PUMP_COUNT = 24                 # pump fleet size; one plot per pump per slot
PUMP_RUNTIME_MIN = 30           # litres/min etc. are Member-3 concerns; M1 only orders plots
TICK_MINUTES = 10               # simulated clock advance per tick

# ----------------------------------------------------------------------------
# Crop / agronomy constants used by the stress model
# ----------------------------------------------------------------------------
CROPS = {
    "Paddy": 1.15, "Sugarcane": 1.25, "Tomato": 1.05, "Maize": 0.95,
    "Onion": 1.00, "Groundnut": 0.90, "Ragi": 0.85, "Cotton": 1.10,
}
VILLAGES = (
    "Kadugodi", "Hosakere", "Bidalur", "Yelahanka",
    "Doddaballapur", "Nelamangala", "Anekal", "Kanakapura",
)

TARGET_MOISTURE = 45.0          # % volumetric, above this the plot is comfortable
CRITICAL_MOISTURE = 15.0        # % below this an emergency alert is raised
TEMP_COMFORT_HI = 30.0          # deg C, above this heat adds stress
HUMIDITY_COMFORT_LO = 45.0      # % below this dry air adds stress
RAIN_COMFORT = 6.0              # mm in the last 24 h that counts as "watered by sky"

# Weights must sum to SCORE_MAX (1000) before the crop coefficient is applied.
W_MOISTURE = 450
W_TEMP = 250
W_HUMIDITY = 150
W_RAIN = 150

# Status bands derived from the score
STATUS_BANDS = (
    (700, "CRITICAL"),
    (450, "HIGH"),
    (250, "MODERATE"),
    (0, "OK"),
)


def status_for_score(score: int) -> str:
    """Map a 0..1000 water-stress score onto a status band."""
    for threshold, name in STATUS_BANDS:
        if score >= threshold:
            return name
    return "OK"


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else (high if value > high else value)


# ----------------------------------------------------------------------------
# Record factories -- THE SHARED CONTRACT
# ----------------------------------------------------------------------------
def make_plot(plot_id: int, rng: random.Random) -> dict:
    """Return one Plot record.  Fields marked (M2/M3) are filled by other members."""
    village = VILLAGES[plot_id % len(VILLAGES)]
    return {
        # ---- identity (M3 registry) ----
        "plot_id": plot_id,                      # int, 1..MAX_PLOTS
        "farmer_id": 1000 + (plot_id % 700),
        "village": village,
        "crop": list(CROPS)[plot_id % len(CROPS)],
        "area_acres": round(0.5 + (plot_id % 47) * 0.25, 2),
        # ---- geometry (M2 quad-tree) ----
        "x": round(12.7000 + rng.random() * 0.3500, 6),
        "y": round(77.4000 + rng.random() * 0.3500, 6),
        "ndvi": round(rng.uniform(0.18, 0.82), 3),      # simulated, M2
        "water_source": f"SRC-{(plot_id % 6) + 1}",
        # ---- latest sensor reading (M1 simulator) ----
        "moisture": round(rng.uniform(12.0, 58.0), 2),
        "temperature": round(rng.uniform(21.0, 37.0), 2),
        "humidity": round(rng.uniform(25.0, 78.0), 2),
        "rainfall": round(max(0.0, rng.gauss(1.2, 2.4)), 2),
        # ---- derived by Member 1 ----
        "stress_score": 0,                       # int 0..1000
        "status": "OK",                          # OK | MODERATE | HIGH | CRITICAL
        "trend": 0.0,                            # stress delta over the sliding window
        "pump_id": None,                         # assigned by the scheduler
        "last_irrigated_tick": None,
        "score_updated_tick": 0,
    }


def make_reading(plot_id: int, tick: int, plot: dict) -> dict:
    """Return one Reading record (what a field sensor would POST)."""
    return {
        "plot_id": plot_id,
        "tick": tick,
        "timestamp": None,                        # filled by the simulator clock
        "moisture": plot["moisture"],
        "temperature": plot["temperature"],
        "humidity": plot["humidity"],
        "rainfall": plot["rainfall"],
    }


def make_schedule_row(slot_index: int, window_key: str, slot_label: str,
                      pump_id: str, plot: dict, rank: int) -> dict:
    """Return one Schedule row (what the Pump Scheduler timeline renders)."""
    return {
        "slot_index": slot_index,                 # 0..TOTAL_SLOTS-1
        "window": window_key,                     # "morning" | "evening"
        "slot_label": slot_label,                 # "05:00-05:30"
        "pump_id": pump_id,
        "plot_id": plot["plot_id"],
        "village": plot["village"],
        "crop": plot["crop"],
        "priority_rank": rank,                    # 1 = highest priority
        "stress_score": plot["stress_score"],
        "status": plot["status"],
        "runtime_minutes": PUMP_RUNTIME_MIN,
        "eta_litres": round(plot["area_acres"] * 420.0, 1),
        "reason": None,                           # filled by the scheduler (why chosen)
    }


def make_alert(alert_id: int, tick: int, timestamp: str, severity: str,
               kind: str, plot_id, message: str) -> dict:
    """Return one Alerts-panel entry."""
    return {
        "alert_id": alert_id,
        "tick": tick,
        "timestamp": timestamp,
        "severity": severity,                     # info | warning | critical
        "kind": kind,                             # moisture | trend | pump | grid | ...
        "plot_id": plot_id,
        "message": message,
        "acknowledged": False,
    }
