/**
 * KJS-AGR-01 | Member 1: Priority & Scheduling Engine
 * M1Module.jsx -- the whole Member-1 surface: header, live data-structure strip,
 * and the four pages from the work-distribution sheet.
 *
 * INTEGRATION NOTE (for Member 3): drop this component inside the AppShell and
 * it inherits nothing but the page background, so it will not fight the theme.
 * Remove the .m1-shell wrapper if the shell already provides padding.
 */
import React, { useState } from 'react';
import useM1Polling from './useM1Polling';
import PriorityBoard from './PriorityBoard';
import PumpScheduleTimeline from './PumpScheduleTimeline';
import AlertsPanel from './AlertsPanel';
import SimulationControls from './SimulationControls';
import BenchmarkPanel from './BenchmarkPanel';
import { DataStructureStrip, fmt } from './ui';
import './m1.css';

const TABS = [
  { id: 'board', label: 'Live Priority Board' },
  { id: 'schedule', label: 'Pump Scheduler' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'controls', label: 'Controls' },
  { id: 'benchmarks', label: 'Benchmarks' },
];

export default function M1Module() {
  const [tab, setTab] = useState('board');
  const { state, error, loading, lastUpdated, paused, setPaused, refresh } = useM1Polling(2000);

  const meta = state?.meta || {};
  const counts = state?.counts || {};

  return (
    <div className="m1-shell">
      <header className="m1-header">
        <div className="m1-header__id">
          <div className="m1-header__badge">M1</div>
          <div>
            <h1 className="m1-header__title">Priority &amp; Scheduling Engine</h1>
            <p className="m1-header__sub">
              Indexed max-heap · circular queue · deque · counting / bubble / insertion / heap sort
              <span className="m1-muted"> — KJS-AGR-01</span>
            </p>
          </div>
        </div>

        <div className="m1-header__right">
          <div className="m1-live">
            <span className={`m1-live__dot${paused ? ' m1-live__dot--paused' : ''}`} />
            {paused ? 'polling paused' : 'live'}
            {lastUpdated ? <span className="m1-muted"> · {lastUpdated.toLocaleTimeString()}</span> : null}
          </div>
          <div className="m1-header__clock">
            <strong>{meta.clock || '—'}</strong>
            <span className="m1-muted">tick {fmt(meta.tick)}</span>
          </div>
          <button className="m1-btn m1-btn--ghost" onClick={refresh}>↻</button>
        </div>
      </header>

      {error ? (
        <div className="m1-banner m1-banner--error">
          Cannot reach the Member-1 API ({error}). Start Flask with <code>python app.py</code> —
          the blueprint is mounted at <code>/api/priority</code>.
        </div>
      ) : null}

      <div className="m1-kpis">
        <Kpi label="Plots simulated" value={fmt(counts.plots)} />
        <Kpi label="Critical" value={fmt(counts.critical)} tone="err" />
        <Kpi label="High" value={fmt(counts.high)} tone="warn" />
        <Kpi label="Pump seats filled" value={fmt(state?.schedule?.summary?.seats_filled)} tone="ok" />
        <Kpi label="Scheduled plots" value={fmt(counts.scheduled)} />
        <Kpi label="Irrigated so far" value={fmt(counts.irrigated_total)} />
      </div>

      <DataStructureStrip ds={state?.data_structures} lastTick={state?.last_tick} />

      <nav className="m1-tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`m1-tab${tab === t.id ? ' m1-tab--on' : ''}`}
                  onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className="m1-body">
        {loading && !state ? <div className="m1-muted">connecting to the simulator…</div> : null}
        {tab === 'board' && <PriorityBoard tick={meta.tick} />}
        {tab === 'schedule' && <PumpScheduleTimeline state={state} />}
        {tab === 'alerts' && <AlertsPanel state={state} />}
        {tab === 'controls' && (
          <SimulationControls state={state} refresh={refresh} paused={paused} setPaused={setPaused} />
        )}
        {tab === 'benchmarks' && <BenchmarkPanel />}
      </main>

      <footer className="m1-footer">
        <span>Member 1 of 3 · data structures, backend and UI for the Priority &amp; Scheduling module</span>
        <span className="m1-muted">
          windows 05:00–08:00 and 14:00–17:00 · {fmt(state?.schedule?.summary?.seats_total)} pump seats per cycle
        </span>
      </footer>
    </div>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className={`m1-kpi${tone ? ` m1-kpi--${tone}` : ''}`}>
      <div className="m1-kpi__v">{value}</div>
      <div className="m1-kpi__l">{label}</div>
    </div>
  );
}
