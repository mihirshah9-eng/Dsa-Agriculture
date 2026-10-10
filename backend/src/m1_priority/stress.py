"""
KJS-AGR-01  |  Member 1: Priority & Scheduling Engine
stress.py -- water-stress score (the heap's priority key).

Score model (0..1000, INTEGER so counting sort applies):

    score = clamp( W_m*f_moisture + W_t*f_temp + W_h*f_humidity + W_r*f_rain ) * crop_coefficient

    f_moisture = (TARGET - moisture) / TARGET              -> 0..450   weight 45%
    f_temp     = (temperature - 30) / 16                   -> 0..250   weight 25%
    f_humidity = (45 - humidity) / 45                      -> 0..150   weight 15%
    f_rain     = (6 - rainfall_24h) / 6                    -> 0..150   weight 15%

Rationale for the weights: soil moisture dominates because it is the quantity
the pump actually changes; temperature/humidity drive the *rate* of loss
(evapotranspiration) and rainfall is a slow-moving offset.  The crop
coefficient (Paddy 1.15, Ragi 0.85 ...) expresses that the same moisture deficit
hurts a water-hungry crop more.

Every function here is O(1): the score is computed per plot, and the *ordering*
of 25,000 scores is the heap's job, not this file's.
"""
from __future__ import annotations

from .schema import (
    CRITICAL_MOISTURE, CROPS, HUMIDITY_COMFORT_LO, RAIN_COMFORT, SCORE_MAX,
    SCORE_MIN, TARGET_MOISTURE, TEMP_COMFORT_HI, W_HUMIDITY, W_MOISTURE,
    W_RAIN, W_TEMP, clamp, status_for_score,
)


def water_stress_score(moisture: float, temperature: float, humidity: float,
                       rainfall: float, crop: str = "Maize",
                       drought_factor: float = 1.0,
                       heat_factor: float = 1.0) -> int:
    """O(1).  Returns an integer score in [0, 1000]; higher = more urgent."""
    # --- moisture deficit (dominant term) --------------------------------
    f_moisture = clamp((TARGET_MOISTURE - moisture) / TARGET_MOISTURE, 0.0, 1.0)
    f_moisture = clamp(f_moisture * drought_factor, 0.0, 1.0)

    # --- heat / evapotranspiration --------------------------------------
    f_temp = clamp((temperature - TEMP_COMFORT_HI) / 16.0, 0.0, 1.0)
    f_temp = clamp(f_temp * heat_factor, 0.0, 1.0)

    # --- dry air ---------------------------------------------------------
    f_humidity = clamp((HUMIDITY_COMFORT_LO - humidity) / HUMIDITY_COMFORT_LO, 0.0, 1.0)

    # --- no rain in the last 24 h ---------------------------------------
    f_rain = clamp((RAIN_COMFORT - rainfall) / RAIN_COMFORT, 0.0, 1.0)

    raw = (W_MOISTURE * f_moisture
           + W_TEMP * f_temp
           + W_HUMIDITY * f_humidity
           + W_RAIN * f_rain)

    crop_coefficient = CROPS.get(crop, 1.0)
    return int(clamp(round(raw * crop_coefficient), SCORE_MIN, SCORE_MAX))


def score_plot(plot: dict, drought_factor: float = 1.0, heat_factor: float = 1.0) -> int:
    score = water_stress_score(
        moisture=plot["moisture"], temperature=plot["temperature"],
        humidity=plot["humidity"], rainfall=plot["rainfall"], crop=plot["crop"],
        drought_factor=drought_factor, heat_factor=heat_factor,
    )
    plot["stress_score"] = score
    plot["status"] = status_for_score(score)
    return score


def is_emergency(plot: dict) -> bool:
    """Below the critical soil-moisture line, regardless of the composite score."""
    return plot["moisture"] < CRITICAL_MOISTURE


def explain(plot: dict, drought_factor: float = 1.0) -> dict:
    """Per-term breakdown -- the Alerts panel shows this in the plot popup, and
    it is the fastest way to defend the formula in the viva."""
    moisture, temperature = plot["moisture"], plot["temperature"]
    humidity, rainfall = plot["humidity"], plot["rainfall"]
    f_moisture = clamp((TARGET_MOISTURE - moisture) / TARGET_MOISTURE, 0.0, 1.0)
    f_moisture = clamp(f_moisture * drought_factor, 0.0, 1.0)
    f_temp = clamp((temperature - TEMP_COMFORT_HI) / 16.0, 0.0, 1.0)
    f_humidity = clamp((HUMIDITY_COMFORT_LO - humidity) / HUMIDITY_COMFORT_LO, 0.0, 1.0)
    f_rain = clamp((RAIN_COMFORT - rainfall) / RAIN_COMFORT, 0.0, 1.0)
    parts = {
        "moisture": {"value": round(moisture, 1), "factor": round(f_moisture, 4), "points": round(W_MOISTURE * f_moisture, 1), "weight": W_MOISTURE},
        "temperature": {"value": round(temperature, 1), "factor": round(f_temp, 4), "points": round(W_TEMP * f_temp, 1), "weight": W_TEMP},
        "humidity": {"value": round(humidity, 1), "factor": round(f_humidity, 4), "points": round(W_HUMIDITY * f_humidity, 1), "weight": W_HUMIDITY},
        "rainfall": {"value": round(rainfall, 2), "factor": round(f_rain, 4), "points": round(W_RAIN * f_rain, 1), "weight": W_RAIN},
    }
    coeff = CROPS.get(plot["crop"], 1.0)
    return {
        "plot_id": plot["plot_id"], "crop": plot["crop"], "crop_coefficient": coeff,
        "terms": parts, "subtotal": round(sum(p["points"] for p in parts.values()), 1),
        "score": plot["stress_score"], "status": plot["status"],
        "emergency": is_emergency(plot),
    }


def priority_reason(plot: dict, rank: int) -> str:
    """Human-readable 'why this plot got the pump' string for the schedule row."""
    bits = []
    if plot["moisture"] < CRITICAL_MOISTURE:
        bits.append(f"soil moisture {plot['moisture']:.1f}% below critical")
    else:
        bits.append(f"moisture {plot['moisture']:.1f}%")
    if plot["temperature"] >= TEMP_COMFORT_HI + 4:
        bits.append(f"heat {plot['temperature']:.0f}C")
    if plot.get("trend", 0) and plot["trend"] > 6:
        bits.append(f"drying fast (+{plot['trend']:.0f}/tick)")
    if plot["rainfall"] < 0.5:
        bits.append("no rain 24h")
    bits.append(f"score {plot['stress_score']}")
    return f"R{rank}: " + ", ".join(bits)
