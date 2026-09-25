# Flask API Routes for Priority Engine
from flask import Blueprint, jsonify, request
from .indexed_heap import IndexedMaxHeap
from .sensor_simulator import SensorTelemetrySimulator
from .pump_scheduler import PumpScheduler

m1_bp = Blueprint('m1_priority', __name__)

# Singleton instances for Member 1 state management
heap_engine = IndexedMaxHeap()
simulator = SensorTelemetrySimulator(total_plots=1000)
scheduler = PumpScheduler()

@m1_bp.route('/simulate-telemetry', methods=['POST'])
def simulate_telemetry():
    """Triggers telemetry stream generation and updates Indexed Max-Heap."""
    data = request.get_json() or {}
    batch_size = data.get('batch_size', 50)
    
    updated_nodes = simulator.generate_telemetry_batch(batch_size=batch_size)
    for node in updated_nodes:
        heap_engine.insert_or_update(node)

    return jsonify({
        "status": "success",
        "processed_nodes": len(updated_nodes),
        "total_heap_size": len(heap_engine)
    })

@m1_bp.route('/live-priority', methods=['GET'])
def get_live_priority():
    """Fetches top-priority water-stressed plots from Indexed Max-Heap."""
    k = request.args.get('limit', default=10, type=int)
    top_plots = heap_engine.get_top_k(k=k)
    return jsonify({
        "total_active_plots": len(heap_engine),
        "priority_queue": top_plots
    })

@m1_bp.route('/pump-schedule', methods=['GET'])
def get_pump_schedule():
    """Generates priority pump schedule aligned with electricity windows."""
    top_plots = heap_engine.get_top_k(k=15)
    dispatch_plan = scheduler.generate_schedule(top_plots)
    return jsonify({
        "electricity_windows": scheduler.electricity_windows,
        "dispatch_schedule": dispatch_plan
    })