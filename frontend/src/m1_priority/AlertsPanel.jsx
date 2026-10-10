/**
 * KJS-AGR-01 | Member 1
 * AlertsPanel.jsx -- the alerts stream plus live data-structure vitals.
 *
 * Severity comes from the simulator: grid/system notices are informational,
 * drought and pump events are warnings, and anything that needs a human before
 * the next window is critical.
 */
import React, { useMemo, useState } from 'react';
import { fmt } from './ui';

const SEVERITY = {
  critical: { color: '#e5484d', icon: '⛔', label: 'CRITICAL' },
  warning: { color: '#f76b15', icon: '⚠', label: 'WARNING' },
  info: { color: '#4c6ef5', icon: 'ℹ', label: 'INFO' },
};

const KINDS = ['all', 'moisture', 'environment', 'pump', 'grid', 'system'];

export default function AlertsPanel({ state }) {
  const [filter, setFilter] = useState('all');
  const alerts = state?.alerts || [];

  const counts = useMemo(() => {
    const c = { critical: 0, warning: 0, info: 0 };
    alerts.forEach((a) => { c[a.severity] = (c[a.severity] || 0) + 1; });
    return c;
  }, [alerts]);

  const visible = filter === 'all' ? alerts : alerts.filter((a) => a.kind === filter);

  return (
    <div className="m1-page">
      <div className="m1-page__head">
        <div>
          <h2 className="m1-page__title">Alerts Panel</h2>
          <p className="m1-page__sub">
            Raised by the ingestion pipeline as scores cross thresholds. Newest first, capped at 250 entries
            so browser memory stays bounded.
          </p>
        </div>
        <div className="m1-alertcounts">
          {Object.entries(counts).map(([sev, n]) => (
            <span key={sev} className="m1-alertcount" style={{ borderColor: `${SEVERITY[sev].color}66` }}>
              <span style={{ color: SEVERITY[sev].color }}>{SEVERITY[sev].icon}</span> {n}
            </span>
          ))}
        </div>
      </div>

      <div className="m1-filters">
        {KINDS.map((k) => (
          <button key={k} className={`m1-tabbtn${filter === k ? ' m1-tabbtn--on' : ''}`} onClick={() => setFilter(k)}>
            {k}
          </button>
        ))}
      </div>

      <div className="m1-alerts">
        {visible.map((a) => {
          const s = SEVERITY[a.severity] || SEVERITY.info;
          return (
            <div className="m1-alert" key={a.alert_id} style={{ borderLeftColor: s.color }}>
              <div className="m1-alert__top">
                <span className="m1-alert__sev" style={{ color: s.color }}>{s.icon} {s.label}</span>
                <span className="m1-alert__kind">{a.kind}</span>
                <span className="m1-muted">{a.timestamp} · tick {a.tick}</span>
                {a.plot_id ? <span className="m1-alert__plot">plot #{a.plot_id}</span> : null}
              </div>
              <div className="m1-alert__msg">{a.message}</div>
            </div>
          );
        })}
        {!visible.length && <div className="m1-muted">No alerts of this kind yet — run a few ticks.</div>}
      </div>

      <h3 className="m1-h3">Simulation vitals</h3>
      <div className="m1-vitals">
        <Vital label="Plots simulated" value={fmt(state?.counts?.plots)} />
        <Vital label="Critical (score ≥ 700)" value={fmt(state?.counts?.critical)} tone="err" />
        <Vital label="High (450–699)" value={fmt(state?.counts?.high)} tone="warn" />
        <Vital label="Moderate (250–449)" value={fmt(state?.counts?.moderate)} />
        <Vital label="Comfortable (< 250)" value={fmt(state?.counts?.ok)} tone="ok" />
        <Vital label="Scheduled this cycle" value={fmt(state?.counts?.scheduled)} />
        <Vital label="Plots irrigated so far" value={fmt(state?.counts?.irrigated_total)} />
        <Vital label="Rainfall (24 h)" value={`${state?.environment?.rainfall_24h ?? '—'} mm`} />
        <Vital label="Regional humidity" value={`${state?.environment?.regional_humidity ?? '—'}%`} />
        <Vital label="Average moisture" value={`${state?.environment?.avg_moisture ?? '—'}%`} />
        <Vital label="Simulated clock" value={state?.meta?.clock} />
        <Vital label="Tick interval" value={`${state?.meta?.tick_ms ?? '—'} ms`} />
      </div>
    </div>
  );
}

function Vital({ label, value, tone }) {
  return (
    <div className={`m1-vital${tone ? ` m1-vital--${tone}` : ''}`}>
      <div className="m1-vital__v">{value}</div>
      <div className="m1-vital__l">{label}</div>
    </div>
  );
}
