/**
 * KJS-AGR-01 | Member 1
 * SimulationControls.jsx -- Benchmark & Simulation Controls page.
 *
 * Every control maps to exactly one thing the backend can do:
 *   drought slider   -> stress model's drought factor (moisture loss multiplier)
 *   rain / heatwave  -> environment events
 *   power cut        -> sheds the evening window and half the pump fleet
 *   plot-count slider-> re-seeds the farm with a new number of plots
 *   burst            -> floods the circular queue to demonstrate overflow policy
 *   step / pause     -> deterministic demo control (no waiting for the timer)
 */
import React, { useState } from 'react';
import { postControl, postPlotCount, postStep } from './m1Api';
import { fmt } from './ui';

const PLOT_STEPS = [500, 2500, 10000, 25000, 50000];

export default function SimulationControls({ state, refresh, paused, setPaused }) {
  const controls = state?.controls || {};
  const meta = state?.meta || {};
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);
  const [plotCount, setPlotCount] = useState(controls.plot_count || 25000);
  const [speed, setSpeed] = useState(meta.tick_ms || 2000);

  const run = async (label, fn) => {
    setBusy(label);
    setMessage(null);
    try {
      const res = await fn();
      setMessage({ ok: true, text: `${label} → ${JSON.stringify(res).slice(0, 160)}` });
      await refresh();
    } catch (e) {
      setMessage({ ok: false, text: `${label} failed: ${e.message}` });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="m1-page">
      <div className="m1-page__head">
        <div>
          <h2 className="m1-page__title">Simulation Controls</h2>
          <p className="m1-page__sub">
            Drive the demo from here. Every button hits the Flask API and the whole module re-reads
            the new state — no page reload.
          </p>
        </div>
        <div className="m1-clock">
          <div className="m1-clock__time">{meta.clock || '—'}</div>
          <div className="m1-muted">tick {fmt(meta.tick)} · {meta.running ? 'running' : 'paused'}</div>
        </div>
      </div>

      {message && (
        <div className={`m1-banner${message.ok ? '' : ' m1-banner--error'}`}>{message.text}</div>
      )}

      <div className="m1-controls">
        <section className="m1-card">
          <h3>Clock</h3>
          <p className="m1-muted">Step through ticks for a deterministic demo, or let it run.</p>
          <div className="m1-btnrow">
            <button className="m1-btn" disabled={busy === 'Step 1 tick'}
                    onClick={() => run('Step 1 tick', () => postStep(1))}>Step 1 tick</button>
            <button className="m1-btn" disabled={busy === 'Step 3 ticks'}
                    onClick={() => run('Step 3 ticks', () => postStep(3))}>Step 3 ticks</button>
            <button className="m1-btn" disabled={busy === 'Step to next slot'}
                    onClick={() => run('Step to next slot', () => postStep(30))}>Jump 30 ticks (5 h)</button>
            <button className={`m1-btn${paused ? '' : ' m1-btn--ghost'}`}
                    onClick={() => { setPaused(!paused); setMessage({ ok: true, text: paused ? 'UI polling resumed' : 'UI polling paused (simulator keeps ticking)' }); }}>
              {paused ? '▶ Resume UI polling' : '⏸ Pause UI polling'}
            </button>
          </div>
          <label className="m1-field m1-field--range">
            <span>Server tick interval: {speed} ms</span>
            <input type="range" min="300" max="5000" step="100" value={speed}
                   onChange={(e) => setSpeed(Number(e.target.value))}
                   onMouseUp={() => run(`Tick interval ${speed}ms`, () => postControl('speed', speed))}
                   onTouchEnd={() => run(`Tick interval ${speed}ms`, () => postControl('speed', speed))} />
          </label>
        </section>

        <section className="m1-card">
          <h3>Environment</h3>
          <p className="m1-muted">Drought raises the rate at which soil loses moisture.</p>
          <label className="m1-field m1-field--range">
            <span>Drought factor: ×{controls.drought_factor ?? 1}</span>
            <input type="range" min="0.6" max="1.8" step="0.05"
                   value={controls.drought_factor ?? 1}
                   onChange={() => {}}
                   onMouseUp={(e) => run('Drought', () => postControl('drought', Number(e.target.value)))}
                   onTouchEnd={(e) => run('Drought', () => postControl('drought', Number(e.target.value)))} />
          </label>
          <div className="m1-btnrow">
            <button className="m1-btn" onClick={() => run('Rain event', () => postControl('rain', 40))}>
              🌧 Rain (+40 mm)
            </button>
            <button className="m1-btn" onClick={() => run('Heatwave', () => postControl('heatwave'))}>
              🔥 Heatwave
            </button>
            <button className="m1-btn" onClick={() => run('Sensor burst', () => postControl('burst'))}>
              📈 Sensor burst
            </button>
          </div>
        </section>

        <section className="m1-card">
          <h3>Power grid</h3>
          <p className="m1-muted">
            A cut sheds the evening window and half the pump fleet, then rebuilds the schedule
            for the remaining seats.
          </p>
          <button className={`m1-btn m1-btn--wide${controls.power_cut ? ' m1-btn--danger' : ''}`}
                  onClick={() => run('Power cut', () => postControl('power_cut', !controls.power_cut))}>
            {controls.power_cut ? '⚡ Restore power' : '⚡ Trigger power cut'}
          </button>
          <div className="m1-muted" style={{ marginTop: 10 }}>
            Status: <strong>{controls.power_cut ? 'CUT ACTIVE' : 'grid normal'}</strong>
          </div>
        </section>

        <section className="m1-card">
          <h3>Farm size</h3>
          <p className="m1-muted">
            Re-seeds the simulator and rebuilds the heap, queue and deque. Watch tick time scale.
          </p>
          <label className="m1-field m1-field--range">
            <span>Plots: {fmt(plotCount)}</span>
            <input type="range" min="0" max={PLOT_STEPS.length - 1} step="1"
                   value={Math.max(0, PLOT_STEPS.indexOf(plotCount))}
                   onChange={(e) => setPlotCount(PLOT_STEPS[Number(e.target.value)])} />
          </label>
          <div className="m1-btnrow">
            {PLOT_STEPS.map((n) => (
              <button key={n} className={`m1-tabbtn${plotCount === n ? ' m1-tabbtn--on' : ''}`}
                      onClick={() => setPlotCount(n)}>{n >= 1000 ? `${n / 1000}k` : n}</button>
            ))}
          </div>
          <button className="m1-btn m1-btn--wide" disabled={busy === 'Reseed'}
                  onClick={() => run('Reseed', () => postPlotCount(plotCount))}>
            Rebuild simulator with {fmt(plotCount)} plots
          </button>
        </section>

        <section className="m1-card">
          <h3>Reset</h3>
          <p className="m1-muted">Restores the seed, clock and all controls to the start of the demo.</p>
          <button className="m1-btn m1-btn--wide m1-btn--danger"
                  onClick={() => run('Reset', () => postControl('reset'))}>
            ⟲ Reset simulation
          </button>
          <div className="m1-muted" style={{ marginTop: 10 }}>
            Deterministic seed <strong>{meta.seed}</strong> — the same run reproduces every number in the report.
          </div>
        </section>
      </div>
    </div>
  );
}
