# IoT Telemetry Stream Generator for 25,000 Plots
import random
import time
from collections import deque
from .indexed_heap import PlotNode

class CircularQueueBuffer:
    """Fixed-capacity Circular Queue data structure for telemetry ingestion stream."""
    def __init__(self, capacity=1000):
        self.capacity = capacity
        self.queue = deque(maxlen=capacity)

    def enqueue(self, item):
        self.queue.append(item)  # Automatically drops oldest item when capacity is reached

    def dequeue(self):
        if self.is_empty():
            return None
        return self.queue.popleft()

    def is_empty(self):
        return len(self.queue) == 0

    def get_all(self):
        return list(self.queue)


class SensorTelemetrySimulator:
    """Simulates real-time IoT sensor telemetry streams across farm plots."""
    def __init__(self, total_plots=1000):
        self.total_plots = total_plots
        self.buffer = CircularQueueBuffer(capacity=total_plots)
        self.plot_states = {}
        self._initialize_plots()

    def _initialize_plots(self):
        """Initializes default plot states with randomized baseline values."""
        for i in range(1, self.total_plots + 1):
            plot_id = f"PLOT_{i:05d}"
            moisture = random.uniform(15.0, 45.0)
            temp = random.uniform(22.0, 38.0)
            humidity = random.uniform(40.0, 85.0)
            
            self.plot_states[plot_id] = {
                "moisture": moisture,
                "temp": temp,
                "humidity": humidity
            }

    def calculate_stress_score(self, moisture, temp):
        """Derives plot water stress score normalized between 0.0 and 1.0."""
        base_stress = 1.0 - (moisture / 100.0)
        temp_factor = max(0.0, (temp - 25.0) * 0.005)
        return min(1.0, max(0.0, base_stress + temp_factor))

    def generate_telemetry_batch(self, batch_size=50):
        """Generates dynamic telemetry updates and enqueues into circular buffer."""
        updated_nodes = []
        plot_keys = list(self.plot_states.keys())
        selected_plots = random.sample(plot_keys, min(batch_size, len(plot_keys)))

        for plot_id in selected_plots:
            state = self.plot_states[plot_id]
            
            # Simulate natural soil moisture depletion and temperature fluctuation
            state["moisture"] = max(5.0, state["moisture"] - random.uniform(0.1, 0.8))
            state["temp"] = max(18.0, min(42.0, state["temp"] + random.uniform(-0.5, 0.5)))
            state["humidity"] = max(20.0, min(95.0, state["humidity"] + random.uniform(-1.0, 1.0)))

            stress_score = self.calculate_stress_score(state["moisture"], state["temp"])

            node = PlotNode(
                plot_id=plot_id,
                water_stress_score=stress_score,
                soil_moisture=state["moisture"],
                temperature=state["temp"],
                humidity=state["humidity"]
            )

            self.buffer.enqueue(node)
            updated_nodes.append(node)

        return updated_nodes