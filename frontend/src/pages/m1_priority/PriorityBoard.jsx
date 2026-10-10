// Live Priority Board UI Component
import React, { useState, useEffect } from 'react';

const PriorityBoard = () => {
  const [priorityQueue, setPriorityQueue] = useState([]);
  const [schedule, setSchedule] = useState([]);
  const [heapStats, setHeapStats] = useState({ totalPlots: 0 });
  const [loading, setLoading] = useState(false);
  const [batchSize, setBatchSize] = useState(50);

  // Fetch live priority heap data
  const fetchPriorityData = async () => {
    try {
      const res = await fetch('http://127.0.0.1:5000/api/priority/live-priority?limit=10');
      const data = await res.json();
      setPriorityQueue(data.priority_queue || []);
      setHeapStats({ totalPlots: data.total_active_plots || 0 });
    } catch (err) {
      console.error('Error fetching priority queue:', err);
    }
  };

  // Fetch pump dispatch schedule
  const fetchSchedule = async () => {
    try {
      const res = await fetch('http://127.0.0.1:5000/api/priority/pump-schedule');
      const data = await res.json();
      setSchedule(data.dispatch_schedule || []);
    } catch (err) {
      console.error('Error fetching pump schedule:', err);
    }
  };

  // Simulate IoT Telemetry Batch
  const handleTriggerSimulation = async () => {
    setLoading(true);
    try {
      await fetch('http://127.0.0.1:5000/api/simulate-telemetry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ batch_size: Number(batchSize) })
      });
      await fetchPriorityData();
      await fetchSchedule();
    } catch (err) {
      console.error('Simulation trigger failed:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPriorityData();
    fetchSchedule();
  }, []);

  return (
    <div style={{ padding: '24px', fontFamily: 'Arial, sans-serif' }}>
      <h2>Live Priority Board & Pump Scheduler (Member 1)</h2>
      <p style={{ color: '#555' }}>
        Top Pipeline Engine powered by an <strong>Indexed Max-Binary Heap</strong> and <strong>Circular Queue Buffer</strong>.
      </p>

      {/* Control Panel */}
      <div style={{ background: '#fff', padding: '16px', borderRadius: '8px', marginBottom: '24px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
        <h3>Simulation & Telemetry Benchmark Controls</h3>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <label>
            Telemetry Batch Size:
            <input 
              type="number" 
              value={batchSize} 
              onChange={(e) => setBatchSize(e.target.value)}
              style={{ marginLeft: '8px', padding: '6px', width: '80px' }}
            />
          </label>
          <button 
            onClick={handleTriggerSimulation} 
            disabled={loading}
            style={{ padding: '8px 16px', backgroundColor: '#2e7d32', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            {loading ? 'Processing Telemetry...' : 'Simulate IoT Stream Batch'}
          </button>
          <span style={{ fontSize: '14px', color: '#666' }}>Indexed Heap Size: {heapStats.totalPlots} plots</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        {/* Top Priority Table */}
        <div style={{ background: '#fff', padding: '16px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
          <h3>Top Water-Stressed Plots (Max-Heap)</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '12px' }}>
            <thead>
              <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
                <th style={{ padding: '8px' }}>Plot ID</th>
                <th style={{ padding: '8px' }}>Stress Score</th>
                <th style={{ padding: '8px' }}>Soil Moisture</th>
                <th style={{ padding: '8px' }}>Temperature</th>
              </tr>
            </thead>
            <tbody>
              {priorityQueue.map((plot) => (
                <tr key={plot.plot_id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px', fontWeight: 'bold' }}>{plot.plot_id}</td>
                  <td style={{ padding: '8px', color: plot.water_stress_score > 0.7 ? '#d32f2f' : '#ed6c02', fontWeight: 'bold' }}>
                    {plot.water_stress_score}
                  </td>
                  <td style={{ padding: '8px' }}>{plot.soil_moisture}%</td>
                  <td style={{ padding: '8px' }}>{plot.temperature}°C</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pump Dispatch Timeline */}
        <div style={{ background: '#fff', padding: '16px', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
          <h3>Priority Pump Dispatch Timeline</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '12px' }}>
            <thead>
              <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
                <th style={{ padding: '8px' }}>Plot ID</th>
                <th style={{ padding: '8px' }}>Assigned Shift</th>
                <th style={{ padding: '8px' }}>Duration</th>
                <th style={{ padding: '8px' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {schedule.map((item) => (
                <tr key={item.schedule_id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '8px', fontWeight: 'bold' }}>{item.plot_id}</td>
                  <td style={{ padding: '8px' }}>{item.assigned_window} ({item.window_time})</td>
                  <td style={{ padding: '8px' }}>{item.required_duration_hrs} hrs</td>
                  <td style={{ padding: '8px', color: item.status === 'PUMP_ACTIVE' ? '#2e7d32' : '#0288d1', fontWeight: 'bold' }}>
                    {item.status}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default PriorityBoard;