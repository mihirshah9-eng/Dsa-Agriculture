# Priority Pump Dispatching Engine
from collections import deque
import datetime

class PumpScheduler:
    """
    Schedules irrigation pumps by consuming priority plots from the Indexed Max-Heap 
    and fitting them into daily electricity availability windows.
    """
    def __init__(self):
        # Electricity availability windows (24-hr format)
        self.electricity_windows = [
            {"start": "05:00", "end": "08:00", "label": "Morning Shift"},
            {"start": "14:00", "end": "17:00", "label": "Afternoon Shift"},
            {"start": "22:00", "end": "02:00", "label": "Night Shift"}
        ]
        self.dispatch_history = deque(maxlen=100)  # Sliding window history using Deque

    def calculate_required_duration(self, soil_moisture):
        """Calculates needed pump run time in hours based on moisture deficit."""
        target_moisture = 80.0  # Optimal soil moisture percentage
        deficit = max(0.0, target_moisture - soil_moisture)
        # 10% deficit requires approx 0.5 hours of irrigation
        duration_hours = round(max(0.5, min(3.5, deficit * 0.05)), 1)
        return duration_hours

    def generate_schedule(self, prioritized_plots, max_slots=10):
        """
        Maps top water-stressed plots into electricity windows.
        """
        schedule = []
        current_time = datetime.datetime.now()

        for idx, plot in enumerate(prioritized_plots[:max_slots]):
            duration = self.calculate_required_duration(plot["soil_moisture"])
            assigned_window = self.electricity_windows[idx % len(self.electricity_windows)]

            dispatch_entry = {
                "schedule_id": f"SCH_{idx + 1:03d}",
                "plot_id": plot["plot_id"],
                "water_stress_score": plot["water_stress_score"],
                "soil_moisture": plot["soil_moisture"],
                "required_duration_hrs": duration,
                "assigned_window": assigned_window["label"],
                "window_time": f"{assigned_window['start']} - {assigned_window['end']}",
                "status": "SCHEDULED" if idx > 0 else "PUMP_ACTIVE",
                "dispatch_timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S")
            }

            schedule.append(dispatch_entry)
            self.dispatch_history.append(dispatch_entry)

        return schedule

    def get_recent_history(self):
        """Returns sliding-window history from Deque."""
        return list(self.dispatch_history)